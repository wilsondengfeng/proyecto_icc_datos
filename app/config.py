import os


class Config:
    # Puedes dejar vacío si no quieres usar claves
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    API_TOKEN = os.getenv("API_TOKEN", "")
