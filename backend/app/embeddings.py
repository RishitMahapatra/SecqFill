import requests as re 
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

def get_embedding(text: str) -> list[float]: #you pass a string and get a list of numbers in decial
    """
    Calls the local Ollama server to turn text into a vector.
    Ollama must be running locally (ollama serve, or it's already
    running in the background if you've used it before).
    """
    response = re.post(
        OLLAMA_URL,
        json = {"model": EMBED_MODEL, "prompt":text},
    )
    response.raise_for_status()  # throws a clear error if Ollama isn't running
    return response.json()["embedding"]