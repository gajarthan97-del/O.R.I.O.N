"""Run the private, localhost-only ORION application."""
import os
from dotenv import load_dotenv
load_dotenv()
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('orion_app:app', host='127.0.0.1', port=int(os.getenv('ORION_PORT', '8787')), reload=False)
