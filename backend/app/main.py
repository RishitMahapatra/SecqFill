from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import answer_bank, matching, questionnaires

app = FastAPI(title="SecQFill API")

# The Vite dev server runs on a different origin than the API, so without
# this every frontend request fails as a CORS error before it even reaches
# a route handler.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Content-Disposition isn't on the default cross-origin safelist, so
    # without this the frontend can't read the export's real filename from
    # the response and would have to fall back to a generic one.
    # X-Export-Warning carries the known-openpyxl-checkbox-limitation
    # notice (see questionnaires.py) — same exposure problem, same fix.
    expose_headers=["Content-Disposition", "X-Export-Warning"],
)

app.include_router(answer_bank.router)
app.include_router(matching.router)
app.include_router(questionnaires.router)


@app.get("/health")
def health():
    return {"status": "ok"}
