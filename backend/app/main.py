from fastapi import FastAPI

from app.routers import answer_bank, matching

app = FastAPI(title="SecQFill API")

app.include_router(answer_bank.router)
app.include_router(matching.router)


@app.get("/health")
def health():
    return {"status": "ok"}
