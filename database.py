import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta DATABASE_URL en el archivo .env")

# pool_pre_ping evita errores por conexiones muertas si Aurora las cierra por inactividad
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
