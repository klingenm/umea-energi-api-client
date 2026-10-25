"""HTTP routes: login flows, stored tokens and example API calls."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from umea_energi_api_client import (
    ApiError,
    AuthenticatedClient,
    Client,
    CustomerType,
    Login,
    Resolution,
    UmeaEnergiClient,
)
from umea_energi_api_client.generated.types import Response as ApiResponse

from .consumption import KINDS, chart_rows, fetch
from .examples import EXAMPLES, Example, ExampleContext, ExampleUnavailable, format_body
from .models import AuthToken, LoginMethod
from .tokens import LogoutError, RefreshError, TokenManager

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_api(request: Request) -> UmeaEnergiClient:
    return request.app.state.api


def get_tokens(request: Request) -> TokenManager:
    return request.app.state.tokens


Db = Annotated[AsyncSession, Depends(get_db)]
Api = Annotated[UmeaEnergiClient, Depends(get_api)]
Tokens = Annotated[TokenManager, Depends(get_tokens)]
State = Annotated[CustomerType, Form()]


def render(request: Request, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    context.setdefault("login_states", list(CustomerType))
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def redirect(url: Any) -> RedirectResponse:
    return RedirectResponse(str(url), status_code=303)


async def store_token(db: AsyncSession, method: LoginMethod, login: Login) -> AuthToken:
    user = login.user
    token = AuthToken(
        method=method,
        display_name=user.display_name if user else "Unknown user",
        email=user.email if user else None,
        api_user_id=user.id if user else None,
        customer_code=user.customer_code if user else None,
    )
    token.apply(login.credentials)
    db.add(token)
    await db.commit()
    logger.info(
        "%s login succeeded: stored token %d for %s (customer %s, expires %s, refresh token %s)",
        method.value,
        token.id,
        token.display_name,
        token.customer_code,
        token.expires_at,
        "stored" if token.refresh_token else "missing",
    )
    return token


async def get_token(db: AsyncSession, token_id: int) -> AuthToken:
    token = await db.get(AuthToken, token_id)
    if token is None:
        raise HTTPException(404, "No such token")
    return token


@router.get("/", response_class=HTMLResponse, name="index")
async def index(request: Request, db: Db) -> HTMLResponse:
    tokens = await db.scalars(select(AuthToken).order_by(AuthToken.created_at.desc()))
    public_examples = [example for example in EXAMPLES.values() if not example.requires_login]
    return render(request, "index.html", tokens=tokens.all(), examples=public_examples)


# BankID: start an order, then poll it from the browser until the user has signed in.


@router.post("/login/bankid", name="bankid_start", response_model=None)
async def bankid_start(
    request: Request, api: Api, state: State = CustomerType.PRIVATE
) -> HTMLResponse | RedirectResponse:
    try:
        progress = await api.start_bankid(state)
    except ApiError as error:
        logger.warning("BankID start failed: %s", error)
        return render(request, "error.html", 502, title="Couldn't start BankID", error=error)
    logger.info("BankID order %s started", progress.reference)
    url = request.url_for("bankid_page", reference=progress.reference)
    return redirect(url.include_query_params(state=int(state)))


@router.get("/login/bankid/{reference}", response_class=HTMLResponse, name="bankid_page")
async def bankid_page(
    request: Request, reference: str, state: CustomerType = CustomerType.PRIVATE
) -> HTMLResponse:
    return render(request, "login_bankid.html", reference=reference, state=int(state))


@router.get("/login/bankid/{reference}/status", name="bankid_status")
async def bankid_status(
    request: Request,
    reference: str,
    api: Api,
    db: Db,
    state: CustomerType = CustomerType.PRIVATE,
) -> JSONResponse:
    try:
        progress = await api.poll_bankid(reference, state)
    except ApiError as error:
        logger.warning("BankID poll for %s failed: %s", reference, error)
        return JSONResponse({"status": "failed", "error": str(error)}, status_code=502)
    if progress.login is None:
        return JSONResponse(
            {
                "status": "pending",
                "qr_code": progress.qr_code,
                "auto_start_token": progress.auto_start_token,
            }
        )
    token = await store_token(db, LoginMethod.BANKID, progress.login)
    url = request.url_for("token_page", token_id=token.id)
    return JSONResponse({"status": "complete", "redirect": str(url)})


@router.post("/login/bankid/{reference}/cancel", name="bankid_cancel")
async def bankid_cancel(
    request: Request, reference: str, api: Api, state: State = CustomerType.PRIVATE
) -> RedirectResponse:
    # The order may already have expired or completed; there is nothing useful to show then.
    logger.info("Cancelling BankID order %s", reference)
    with suppress(ApiError):
        await api.cancel_bankid(reference, state)
    return redirect(request.url_for("index"))


# Email: username and password first, then the one-time code the API emails to the user.


@router.get("/login/email", response_class=HTMLResponse, name="email_login")
async def email_login(request: Request, state: CustomerType = CustomerType.PRIVATE) -> HTMLResponse:
    return render(request, "login_email.html", step="credentials", state=int(state))


@router.post("/login/email", response_class=HTMLResponse, name="email_start")
async def email_start(
    request: Request,
    api: Api,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    state: State = CustomerType.PRIVATE,
) -> HTMLResponse:
    try:
        await api.start_email_login(username, password, state)
    except ApiError as error:
        logger.warning("Email login step 1 failed for %s: %s", username, error)
        return render(
            request,
            "login_email.html",
            400,
            step="credentials",
            state=int(state),
            username=username,
            error=error,
        )
    logger.info("Email login step 1 accepted for %s; waiting for the emailed code", username)
    return render(request, "login_email.html", step="code", state=int(state), username=username)


@router.post("/login/email/verify", name="email_verify", response_model=None)
async def email_verify(
    request: Request,
    api: Api,
    db: Db,
    username: Annotated[str, Form()],
    code: Annotated[str, Form()],
    state: State = CustomerType.PRIVATE,
) -> HTMLResponse | RedirectResponse:
    try:
        login = await api.complete_email_login(username, code, state)
    except ApiError as error:
        logger.warning("Email login step 2 failed for %s: %s", username, error)
        return render(
            request,
            "login_email.html",
            400,
            step="code",
            state=int(state),
            username=username,
            error=error,
        )
    token = await store_token(db, LoginMethod.EMAIL, login)
    return redirect(request.url_for("token_page", token_id=token.id))


# Stored tokens and example calls.


@router.get("/tokens/{token_id}", response_class=HTMLResponse, name="token_page")
async def token_page(request: Request, token_id: int, db: Db) -> HTMLResponse:
    token = await get_token(db, token_id)
    return render(request, "token.html", token=token, examples=list(EXAMPLES.values()))


@router.post("/tokens/{token_id}/refresh", name="refresh_token", response_model=None)
async def refresh_token(
    request: Request, token_id: int, db: Db, tokens: Tokens
) -> HTMLResponse | RedirectResponse:
    token = await get_token(db, token_id)
    try:
        await tokens.ensure_fresh(db, token, force=True)
    except RefreshError as error:
        return render(request, "error.html", 502, title="Couldn't refresh the token", error=error)
    return redirect(request.url_for("token_page", token_id=token_id))


@router.get("/tokens/{token_id}/consumption", response_class=HTMLResponse, name="consumption")
async def consumption(
    request: Request,
    token_id: int,
    api: Api,
    db: Db,
    tokens: Tokens,
    meter_point: str | None = None,
    kind: str = "consumption",
    start: date | None = None,
    end: date | None = None,
    resolution: Resolution = Resolution.DAY,
    variables: str = "",
) -> HTMLResponse:
    token = await get_token(db, token_id)
    end = end or date.today()
    start = start or end - timedelta(days=30)
    context: dict[str, Any] = {
        "token": token,
        "selected": meter_point,
        "kind": kind,
        "kinds": KINDS,
        "variables": variables,
        "start": start,
        "end": end,
        "resolution": resolution,
        "resolutions": list(Resolution),
        "meter_points": [],
    }
    customer_code = token.customer_code
    if not customer_code:
        return render(
            request, "consumption.html", 400, error="This login has no customer code.", **context
        )
    try:
        token = await tokens.ensure_fresh(db, token)
        points = await api.meter_points(token.access_token, customer_code)
        context["meter_points"] = points
        chosen = next(
            (p for p in points if f"{p.contract_type}:{p.meter_point_no}" == meter_point), None
        )
        if chosen is not None:
            result = await fetch(
                api, kind, token.access_token, chosen, start, end, resolution, variables
            )
            context["rows"] = chart_rows(result)
            context["empty"] = result in ([], {}, None, "")
            context["body"] = json.dumps(result, indent=2, ensure_ascii=False)
    except RefreshError as error:
        return render(request, "consumption.html", 401, error=str(error), **context)
    except ApiError as error:
        return render(request, "consumption.html", 502, error=str(error), **context)
    return render(request, "consumption.html", **context)


@router.post("/tokens/{token_id}/logout", name="logout", response_model=None)
async def logout(
    request: Request, token_id: int, db: Db, tokens: Tokens
) -> HTMLResponse | RedirectResponse:
    token = await get_token(db, token_id)
    try:
        await tokens.logout(db, token)
    except LogoutError as error:
        return render(request, "logout_failed.html", 502, token=token, error=error)
    return redirect(request.url_for("index"))


@router.post("/tokens/{token_id}/delete", name="delete_token")
async def delete_token(request: Request, token_id: int, db: Db) -> RedirectResponse:
    await db.delete(await get_token(db, token_id))
    await db.commit()
    return redirect(request.url_for("index"))


async def call_example(
    api: UmeaEnergiClient, example: Example, token: AuthToken | None
) -> ApiResponse[Any]:
    client: Client | AuthenticatedClient = (
        api.client() if token is None else api.authenticated_client(token.access_token)
    )
    async with client:
        ctx = ExampleContext(api.api_version, client, token.customer_code if token else None)
        return await example.call(ctx)


@router.get("/examples/{slug}", response_class=HTMLResponse, name="run_example")
async def run_example(
    request: Request,
    slug: str,
    api: Api,
    db: Db,
    tokens: Tokens,
    token_id: int | None = None,
) -> HTMLResponse:
    example = EXAMPLES.get(slug)
    if example is None:
        raise HTTPException(404, "No such example")
    token = None if token_id is None else await get_token(db, token_id)
    context: dict[str, Any] = {"example": example, "token": token}
    try:
        if token is not None:
            token = await tokens.ensure_fresh(db, token)
        response = await call_example(api, example, token)
        if response.status_code == 401 and token is not None and token.can_refresh():
            # The API can reject a token before its exp claim says so; refresh and retry once.
            logger.info("Token %d was rejected with 401; refreshing and retrying", token.id)
            token = await tokens.ensure_fresh(db, token, force=True)
            response = await call_example(api, example, token)
    except ExampleUnavailable as error:
        return render(request, "example.html", 400, error=str(error), **context)
    except RefreshError as error:
        return render(request, "example.html", 401, error=str(error), **context)
    except httpx.HTTPError as error:
        return render(request, "example.html", 502, error=f"Request failed: {error}", **context)
    return render(
        request,
        "example.html",
        status=int(response.status_code),
        body=format_body(response.content),
        **context,
    )
