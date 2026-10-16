FROM python:3.12-slim
WORKDIR /function
COPY requirements.resolved.lock /function/requirements.resolved.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.resolved.lock
COPY pyproject.toml /function/
COPY src /function/src
RUN pip install --no-cache-dir --no-deps .
COPY functions/vault_rotation/func.py /function/func.py
# A trusted PostgreSQL CA bundle must be mounted/copied into the image at config.ca_file.
RUN apt-get update && apt-get install -y --only-upgrade liblzma5 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip
RUN useradd --uid 10001 --create-home function
USER 10001
ENTRYPOINT ["/usr/local/bin/fdk", "/function/func.py", "handler"]
