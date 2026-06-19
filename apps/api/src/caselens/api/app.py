from fastapi import FastAPI

app = FastAPI(title="caselens")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
