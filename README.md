## FinMycelium: Collecting Financial Data from Public Sources


> The folder named "EXPERIMENT" will be ignored by git by default. Thus, please always place experimental results under the "EXPERIMENT" folder.


### Environment Configuration

This project uses environment variables for configuration. To get started:

1. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file** with your actual configuration values:
   - Database credentials (MySQL/PostgreSQL)
   - API keys for various services (MinerU, Baidu Search, Bocha Search, LLM services, etc.)
   - Redis configuration (if needed)
   - Proxy settings (optional)

3. **Environment variable loading priority**:
   - The project will first look for `.env` in the current working directory
   - If not found, it will use `.env` in the project root directory
   - Environment variables set in the system will override `.env` file values

> **Note**: Never commit your `.env` file to version control. The `.env.example` file serves as a template showing which variables are needed without exposing sensitive information.

### Structure

```text
.
├── README.md               # Overview of the project.
├── docs/
│   ├── files               # Various documentations.
│   ├── Progress-record.md  # Record of progress and findings.
│   ├── reference.md        # Reference record.
├── configs/                # Configuration files.
├── examples/               # Implemented demos and methods based on `finmy/`.
├── finmy/                  # Codebase of the project.
│   ├── ???
└── requirements.txt        # List of required dependencies.
```

