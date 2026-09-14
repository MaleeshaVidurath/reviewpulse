"""Lambda entrypoint: wraps the FastAPI app (reviewpulse/api.py) with
Mangum so it can run behind a Lambda Function URL.
"""

from mangum import Mangum

from reviewpulse.api import app

handler = Mangum(app, lifespan="off")
