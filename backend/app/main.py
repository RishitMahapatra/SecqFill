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
)

app.include_router(answer_bank.router)
app.include_router(matching.router)
app.include_router(questionnaires.router)


@app.get("/health")
def health():
    return {"status": "ok"}
