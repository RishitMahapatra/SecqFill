from app.embeddings import get_embedding

vec =  get_embedding("Do you encrypt data at rest?")
print(f"Vector length: {len(vec)}")
print(f"First 5 values: {vec[:5]}")
