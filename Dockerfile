# Vertical Spine Kit - single-container image: backend serves the API and the
# built SPA. Canonical shared services mount at runtime via PYTHONPATH
# (compose binds ../shared-canonical-services) - no rebuild needed when
# shared updates.

FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
# Canonical React widgets arrive via the shared build context
# (compose additional_contexts: shared -> ../shared-canonical-services).
COPY --from=shared shared/widgets/react /shared-canonical-services/shared/widgets/react
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim AS prod
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/shared-canonical-services
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-build /frontend/dist /app/frontend/dist
RUN mkdir -p /app/data
EXPOSE 8163
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8163"]
