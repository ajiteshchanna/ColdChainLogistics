# Streamlit Community Cloud deployment

## Prerequisites

1. Push the repository to GitHub without `.env`, `.streamlit/secrets.toml`,
   API keys, passwords, or local database files.
2. Confirm `requirements.txt` contains the runtime dependencies.
3. Create a Streamlit Community Cloud app using the repository and branch.
4. Set the main file to `src/ui.py`.

The application does not require Docker for Community Cloud startup.

## Recommended demo deployment

Set the following in **App settings > Secrets**:

```toml
REEFERTWIN_MODE = "demo"
REEFERTWIN_AI_ENABLED = "false"
```

Demo mode provides the deterministic Overview, Digital Twin, Fleet,
Simulation Lab, What-if Lab, and User Manual pages. It does not claim SQL
persistence or live telemetry. The AI Command Centre reports that no AI
backend is configured, and Audit reports that SQL-backed logs are unavailable.

## Optional integrations

External services are not required for the deterministic demo.

### SQL Server

Use a hosted, reachable SQL Server endpoint. Do not configure
`127.0.0.1`, `localhost`, or a Docker service name in Community Cloud; those
refer to the Streamlit container, not a local developer machine.

```toml
SQL_SERVER_HOST = "sql.example.com"
SQL_SERVER_PORT = "1433"
SQL_DATABASE = "cold_chain"
SQL_AGENT_USER = "USR_FDE_RO"
SQL_AGENT_PASSWORD = "replace-with-a-secret"
```

Admin credentials should not be configured unless the Audit workflow is
explicitly required and the account is protected separately.

### AI backend

The default local provider is Ollama, which is not reachable from Community
Cloud unless hosted and explicitly configured. For a hosted DeepSeek backend:

```toml
REEFERTWIN_MODE = "local"
REEFERTWIN_AI_ENABLED = "true"
Agent_llm = "DEEPSEEK"
DEEPSEEK_API_KEY = "replace-with-a-secret"
```

Do not set `REEFERTWIN_AI_ENABLED=true` without a reachable provider.

### Pinecone SOP retrieval

Pinecone is optional and is only contacted when the SOP search tool is used:

```toml
PINECONE_API_KEY = "replace-with-a-secret"
Embeddings_model = "LOCAL"
Local_Embedding_Model = "BAAI/bge-m3"
```

Missing Pinecone configuration produces a degraded tool result; it does not
prevent the dashboard from starting.

## Configuration precedence

For each supported key, the application uses:

1. Process environment variable
2. Streamlit secrets
3. Optional repository `.env`
4. Safe non-secret default, where defined

The `.env` file is never required in Community Cloud. Streamlit secrets are
read as flat keys and are never printed.

## Security settings

The checked-in Streamlit configuration keeps XSRF protection enabled, binds
the server to its configured runtime interface, and does not disable security
protections to work around startup failures. Never put credentials in source,
logs, exception messages, screenshots, or the UI.

Use a read-only SQL account for telemetry access. Keep approval gates enabled
for scenario actions and do not represent in-memory demo state as persistent
state.

## Troubleshooting

- **Environment file not found:** This should not occur after the lazy
  configuration change. Remove any code or secret that assumes `.env` exists.
- **AI unavailable:** Use demo mode, or configure a reachable hosted provider
  and set `REEFERTWIN_AI_ENABLED=true`.
- **SQL unavailable:** Verify the hosted hostname, firewall, port, ODBC
  compatibility, and credentials. Do not use `localhost`.
- **Pinecone unavailable:** Confirm `PINECONE_API_KEY`; the deterministic pages
  remain usable without it.
- **Import or dependency failure:** Review Community Cloud build logs and
  ensure the selected Python runtime supports the pinned dependencies.

## Local development

Local `.env` loading remains supported. Existing environment variables take
precedence over both `.env` and Streamlit secrets. For deterministic local
operation without external services, use:

```dotenv
REEFERTWIN_MODE=demo
REEFERTWIN_AI_ENABLED=false
```

Run:

```powershell
streamlit run src\ui.py
```

Cloud deployment must still be verified on the actual deployed app; local
tests and import checks do not constitute a cloud deployment claim.
