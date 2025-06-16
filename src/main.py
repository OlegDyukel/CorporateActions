from fastapi import FastAPI

app = FastAPI(title="CorporateActions API")

@app.get("/")
def read_root():
    return {"message": "Welcome to CorporateActions"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
