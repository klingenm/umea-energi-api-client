---
default: patch
---

# Read the access token returned by the production API

The production login endpoints return the JWT as `token.access_token`, which the OpenAPI document doesn't list, so the generated `UmeaEnergiApiModelsLoginAccessToken` model dropped it. The model now has an `access_token` attribute alongside `access_jwt_token`.
