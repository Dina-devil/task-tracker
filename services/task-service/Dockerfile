FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto/ ./proto/
RUN python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/workspace.proto
COPY services/task-service/src ./src
COPY services/task-service/tests ./tests
ENV PYTHONPATH=/app
CMD ["uvicorn", "src.presentation.api:app", "--host", "0.0.0.0", "--port", "8000"]
