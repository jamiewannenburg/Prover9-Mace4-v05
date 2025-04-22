# Prover9-Mace4 Web UI

A modern browser-based user interface for Prover9 and Mace4 based on PyWebIO.

## Features

- Browser-based interface (works on desktop, tablet, and mobile)
- Modern, responsive design
- Easy to deploy via Docker
- Preserves all the functionality of the original wxPython GUI
- Syntax highlighting for input and output

## Installation and Usage

### Option 1: Run with Python directly

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the application:
   ```
   python web_app.py
   ```

3. Open your browser and go to http://localhost:8080

### Option 2: Run with Docker

1. Build and start the container using Docker Buildx (recommended method):
   ```
   # Enable BuildKit by default (only needed once)
   export DOCKER_BUILDKIT=1
   
   # Build and run with docker-compose
   docker compose up -d
   ```

   Alternatively, you can use the classic Docker build method:
   ```
   docker compose up -d
   ```

2. Open your browser and go to http://localhost:8080

### Option 3: Build using Docker Buildx CLI directly

If you want to use advanced Buildx features:

```bash
# Create a new builder instance (first time only)
docker buildx create --name mybuilder --use

# Build the image
docker buildx build -t prover9-mace4-web .

# Run the container
docker run -p 8080:8080 -d prover9-mace4-web
```

This method allows multi-platform builds and other advanced features.

## Usage

The web interface is organized similarly to the original wxPython GUI:

1. **Setup Panel**: Configure inputs and options
   - Formulas: Enter assumptions and goals
   - Language Options: Set language-specific options
   - Prover9 Options: Configure Prover9-specific settings
   - Mace4 Options: Configure Mace4-specific settings
   - Additional Input: Enter any additional input

2. **Run Panel**: Execute and view results
   - Prover9: Run the theorem prover and view results
   - Mace4: Run the model finder and view results

## Sample Workflow

1. Enter assumptions and goals in the Formula tab
2. Set desired options in the Prover9 or Mace4 tabs
3. Switch to the Run tab and click "Start Prover9" or "Start Mace4"
4. View the results in the output area

## License

This project is licensed under the GNU General Public License v2.0.

## Credits

- Original Prover9-Mace4 by William McCune
- Web UI implementation using PyWebIO 