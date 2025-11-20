#!/bin/bash

# Script to convert a pip requirements file to Poetry configuration
# using only standard Bash tools (no python/poetry required at runtime).

# Exit on error
set -e

# Function to print usage instructions
print_usage() {
    echo "Usage: $(basename "$0") <requirements_file> [python_version]"
    echo ""
    echo "Description:"
    echo "  Converts a pip requirements file into 'pyproject.toml' and 'poetry.toml'"
    echo "  configured to use a local .venv folder."
    echo ""
    echo "Arguments:"
    echo "  <requirements_file>  Path to the requirements file (e.g., requirements.txt)"
    echo "  [python_version]     Target Python version (default: 3.12)"
    echo ""
    echo "Examples:"
    echo "  ./$(basename "$0") requirements.txt"
    echo "  ./$(basename "$0") requirements.txt 3.10"
}

# 1. Check Arguments
if [ -z "$1" ]; then
    print_usage
    exit 1
fi

INPUT_FILE="$1"
PYTHON_VERSION="${2:-3.12}"

# 2. Validate Input File
if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: File '$INPUT_FILE' not found."
    exit 1
fi

PROJECT_NAME=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/-/g')

echo "--------------------------------------------------"
echo "Processing '$INPUT_FILE' for Python ${PYTHON_VERSION}..."

# 3. Generate poetry.toml (Local Configuration)
echo "Creating 'poetry.toml' (Forces local .venv)..."
cat > poetry.toml <<EOF
[virtualenvs]
in-project = true
EOF

# 4. Generate pyproject.toml Header
echo "Creating 'pyproject.toml'..."
cat > pyproject.toml <<EOF
[tool.poetry]
name = "${PROJECT_NAME}"
version = "0.1.0"
description = "Converted from ${INPUT_FILE}"
authors = ["Automated Script <no-reply@example.com>"]
readme = "README.md"

[tool.poetry.dependencies]
python = "^${PYTHON_VERSION}"
EOF

# 5. Parse requirements file and append to dependencies
echo "Parsing requirements..."

while IFS= read -r line || [ -n "$line" ]; do
    # Trim whitespace
    line=$(echo "$line" | xargs)
    
    # Skip empty lines and comments
    if [[ -z "$line" ]] || [[ "$line" == \#* ]]; then
        continue
    fi

    # Skip pip-specific flags (recursive files, editable installs, index URLs)
    if [[ "$line" == -* ]]; then
        echo "  Skipping pip flag: $line"
        continue
    fi

    # Handle complex lines (git URLs, Extras, Environment Markers)
    # Bash string parsing is limited; we comment these out for manual user fix.
    # We look for: git+, http, [, or ;
    if [[ "$line" == *"git+"* ]] || [[ "$line" == *"http"* ]] || [[ "$line" == *"["* ]] || [[ "$line" == *";"* ]]; then
        echo "  Warning: Complex requirement detected. Added as comment: $line"
        echo "  # FIXME: Complex requirement: $line" >> pyproject.toml
        continue
    fi

    # Standard parsing logic:
    # Regex splits the line into:
    # 1. Package Name (alphanumeric, dots, dashes, underscores)
    # 2. The rest (the constraint, e.g., ==1.0.0, >=2.0)
    if [[ "$line" =~ ^([a-zA-Z0-9._-]+)(.*)$ ]]; then
        package_name="${BASH_REMATCH[1]}"
        constraint="${BASH_REMATCH[2]}"
        
        # Trim constraint whitespace
        constraint=$(echo "$constraint" | xargs)

        # If constraint is empty, use wildcard "*"
        if [[ -z "$constraint" ]]; then
            constraint="*"
        fi

        # Write to pyproject.toml
        echo "${package_name} = \"${constraint}\"" >> pyproject.toml
    else
        echo "  # FIXME: Could not parse: $line" >> pyproject.toml
    fi

done < "$INPUT_FILE"

# 6. Append build system configuration
cat >> pyproject.toml <<EOF

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
EOF

echo "--------------------------------------------------"
echo "Conversion complete."
echo ""
echo "Files created:"
echo "  1. poetry.toml    (Configures .venv to live in this folder)"
echo "  2. pyproject.toml (Contains dependencies from $INPUT_FILE)"
echo ""
echo "Next steps:"
echo "  1. Review pyproject.toml (check for # FIXME comments)"
echo "  2. Run: poetry install"