"""HTTP routes: login flows, stored tokens and example API calls."""

from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from umea_energi_api_client import AuthenticatedClient, Client

from .api import ApiError, LoginManagerState, LoginResult, UmeaEnergiApi
from .examples import EXAMPLES, ExampleContext, ExampleUnavailable, format_body
from .models import AuthToken, LoginMethod, jwt_expiry

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_api(request: Request) -> UmeaEnergiApi:
    return request.app.state.api


Db = Annotated[AsyncSession, Depends(get_db)]
Api = Annotated[UmeaEnergiApi, Depends(get_api)]
State = Annotated[LoginManagerState, Form()]


def render(request: Request, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    context.setdefault("login_states", list(LoginManagerState))
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def redirect(url: Any) -> RedirectResponse:
    return RedirectResponse(str(url), status_code=303)


async def store_token(db: AsyncSession, method: LoginMethod, result: LoginResult) -> AuthToken:
    token = AuthToken(
        method=method,
        display_name=result.display_name,
        email=result.email,
        api_user_id=result.api_user_id,
        customer_code=result.customer_code,
        access_token=result.access_token,
        expires_at=jwt_expiry(result.access_token),
    )
    db.add(token)
    await db.commit()
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
    request: Request, api: Api, state: State = LoginManagerState.VALUE_0
) -> HTMLResponse | RedirectResponse:
    try:
        progress = await api.start_bankid(state)
    except ApiError as error:
        return render(request, "error.html", 502, title="Couldn't start BankID", error=error)
    url = request.url_for("bankid_page", reference=progress.reference)
    return redirect(url.include_query_params(state=int(state)))


@router.get("/login/bankid/{reference}", response_class=HTMLResponse, name="bankid_page")
async def bankid_page(
    request: Request, reference: str, state: LoginManagerState = LoginManagerState.VALUE_0
) -> HTMLResponse:
    return render(request, "login_bankid.html", reference=reference, state=int(state))


@router.get("/login/bankid/{reference}/status", name="bankid_status")
async def bankid_status(
    request: Request,
    reference: str,
    api: Api,
    db: Db,
    state: LoginManagerState = LoginManagerState.VALUE_0,
) -> JSONResponse:
    try:
        progress = await api.poll_bankid(reference, state)
    except ApiError as error:
        return JSONResponse({"status": "failed", "error": str(error)}, status_code=502)
    if progress.result is None:
        return JSONResponse(
            {
                "status": "pending",
                "qr_code": progress.qr_code,
                "auto_start_token": progress.auto_start_token,
            }
        )
    token = await store_token(db, LoginMethod.BANKID, progress.result)
    url = request.url_for("token_page", token_id=token.id)
    return JSONResponse({"status": "complete", "redirect": str(url)})


@router.post("/login/bankid/{reference}/cancel", name="bankid_cancel")
async def bankid_cancel(
    request: Request, reference: str, api: Api, state: State = LoginManagerState.VALUE_0
) -> RedirectResponse:
    # The order may already have expired or completed; there is nothing useful to show then.
    with suppress(ApiError):
        await api.cancel_bankid(reference, state)
    return redirect(request.url_for("index"))


# Email: username and password first, then the one-time code the API emails to the user.


@router.get("/login/email", response_class=HTMLResponse, name="email_login")
async def email_login(
    request: Request, state: LoginManagerState = LoginManagerState.VALUE_0
) -> HTMLResponse:
    return render(request, "login_email.html", step="credentials", state=int(state))


@router.post("/login/email", response_class=HTMLResponse, name="email_start")
async def email_start(
    request: Request,
    api: Api,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    state: State = LoginManagerState.VALUE_0,
) -> HTMLResponse:
    try:
        await api.start_email_login(username, password, state)
    except ApiError as error:
        return render(
            request,
            "login_email.html",
            400,
            step="credentials",
            state=int(state),
            username=username,
            error=error,
        )
    return render(request, "login_email.html", step="code", state=int(state), username=username)


@router.post("/login/email/verify", name="email_verify", response_model=None)
async def email_verify(
    request: Request,
    api: Api,
    db: Db,
    username: Annotated[str, Form()],
    code: Annotated[str, Form()],
    state: State = LoginManagerState.VALUE_0,
) -> HTMLResponse | RedirectResponse:
    try:
        result = await api.complete_email_login(username, code.strip(), state)
    except ApiError as error:
        return render(
            request,
            "login_email.html",
            400,
            step="code",
            state=int(state),
            username=username,
            error=error,
        )
    token = await store_token(db, LoginMethod.EMAIL, result)
    return redirect(request.url_for("token_page", token_id=token.id))


# Stored tokens and example calls.


@router.get("/tokens/{token_id}", response_class=HTMLResponse, name="token_page")
async def token_page(request: Request, token_id: int, db: Db) -> HTMLResponse:
    token = await get_token(db, token_id)
    return render(request, "token.html", token=token, examples=list(EXAMPLES.values()))


@router.post("/tokens/{token_id}/delete", name="delete_token")
async def delete_token(request: Request, token_id: int, db: Db) -> RedirectResponse:
    await db.delete(await get_token(db, token_id))
    await db.commit()
    return redirect(request.url_for("index"))


@router.get("/examples/{slug}", response_class=HTMLResponse, name="run_example")
async def run_example(
    request: Request, slug: str, api: Api, db: Db, token_id: int | None = None
) -> HTMLResponse:
    example = EXAMPLES.get(slug)
    if example is None:
        raise HTTPException(404, "No such example")
    token = None if token_id is None else await get_token(db, token_id)
    client: Client | AuthenticatedClient = (
        api.client() if token is None else api.authenticated_client(token.access_token)
    )
    context: dict[str, Any] = {"example": example, "token": token}
    async with client:
        ctx = ExampleContext(api.version, client, token.customer_code if token else None)
        try:
            response = await example.call(ctx)
        except ExampleUnavailable as error:
            return render(request, "example.html", 400, error=str(error), **context)
        except httpx.HTTPError as error:
            return render(request, "example.html", 502, error=f"Request failed: {error}", **context)
    return render(
        request,
        "example.html",
        status=int(response.status_code),
        body=format_body(response.content),
        **context,
    )
