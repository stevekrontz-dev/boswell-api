"""
Boswell MCPB Bundle Builder

Generates .mcpb (MCP Bundle) files for distribution to users.
"""

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import tempfile
import shutil


@dataclass
class BundleConfig:
    """Configuration for bundle generation."""
    tenant_id: str
    api_key: str
    display_name: Optional[str] = None

    # Boswell API endpoint
    api_endpoint: str = "https://boswell-api-production.up.railway.app"


@dataclass
class BundleResult:
    """Result of bundle generation."""
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None
    manifest: Optional[dict] = None


class BundleBuilder:
    """
    Builds personalized .mcpb bundles for Boswell users.

    The bundle contains:
    - manifest.json with user_config for API credentials
    - Node.js MCP server code (pre-bundled with dependencies)
    - Icon and metadata

    Usage:
        builder = BundleBuilder(template_dir=Path("extension/templates"))
        result = builder.build(
            config=BundleConfig(tenant_id="abc123", api_key="bos_xxx"),
            output_path=Path("boswell.mcpb")
        )
    """

    MANIFEST_VERSION = "0.3"
    BUNDLE_VERSION = "1.0.0"

    def __init__(self, template_dir: Path, server_dir: Optional[Path] = None):
        """
        Initialize the bundle builder.

        Args:
            template_dir: Directory containing template files (manifest.template.json)
            server_dir: Directory containing MCP server code to bundle
        """
        self.template_dir = template_dir
        self.server_dir = server_dir or template_dir.parent / "server"

    def build(self, config: BundleConfig, output_path: Path) -> BundleResult:
        """
        Build a personalized .mcpb bundle.

        Args:
            config: Bundle configuration with tenant credentials
            output_path: Where to write the .mcpb file

        Returns:
            BundleResult with success status and details
        """
        try:
            # 1. Load manifest template
            manifest = self._load_manifest_template()

            # 2. Inject user_config with tenant_id and api_key
            manifest = self._inject_user_config(manifest, config)

            # 3. Update display name if provided
            if config.display_name:
                manifest["display_name"] = f"Boswell Memory - {config.display_name}"

            # 4. Create ZIP archive with manifest and server files
            self._create_zip(manifest, output_path)

            return BundleResult(
                success=True,
                output_path=output_path,
                manifest=manifest
            )

        except FileNotFoundError as e:
            return BundleResult(
                success=False,
                error=f"Template or server files not found: {e}"
            )
        except Exception as e:
            return BundleResult(
                success=False,
                error=f"Bundle creation failed: {e}"
            )

    def _load_manifest_template(self) -> dict:
        """Load and parse the manifest template."""
        template_path = self.template_dir / "manifest.template.json"
        with open(template_path) as f:
            return json.load(f)

    def _inject_user_config(self, manifest: dict, config: BundleConfig) -> dict:
        """Inject tenant-specific configuration into manifest."""
        # The user_config defines fields that Claude Desktop will prompt for
        # or that we pre-fill with the user's credentials
        manifest["user_config"] = {
            "api_key": {
                "type": "string",
                "title": "Boswell API Key",
                "description": "Your Boswell API key for authentication",
                "required": True,
                "sensitive": True,
                "default": config.api_key  # Pre-filled for this user
            },
            "tenant_id": {
                "type": "string",
                "title": "Tenant ID",
                "description": "Your Boswell tenant identifier",
                "required": True,
                "default": config.tenant_id  # Pre-filled for this user
            },
            "api_endpoint": {
                "type": "string",
                "title": "API Endpoint",
                "description": "Boswell API endpoint URL",
                "required": True,
                "default": config.api_endpoint
            }
        }
        return manifest

    def _create_zip(self, manifest: dict, output_path: Path) -> None:
        """Create the .mcpb ZIP archive."""
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # Copy server files
            if self.server_dir.exists():
                for file_path in self.server_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = f"server/{file_path.relative_to(self.server_dir)}"
                        zf.write(file_path, arcname)

    def validate(self, mcpb_path: Path) -> BundleResult:
        """
        Validate an existing .mcpb bundle.

        Args:
            mcpb_path: Path to the .mcpb file

        Returns:
            BundleResult with validation status
        """
        # STUB: W4P2 implementation
        return BundleResult(
            success=False,
            error="Not implemented"
        )


def generate_bundle_for_user(tenant_id: str, api_key: str, display_name: Optional[str] = None) -> bytes:
    """
    Generate a bundle for a user and return as bytes.

    This function is called by the /api/extension/download endpoint.

    Args:
        tenant_id: User's tenant ID
        api_key: User's API key
        display_name: Optional display name for personalization

    Returns:
        Bytes of the .mcpb file for streaming response
    """
    # Determine paths relative to this file
    builder_dir = Path(__file__).parent
    extension_dir = builder_dir.parent
    template_dir = extension_dir / "templates"
    server_dir = extension_dir / "server"

    # Create builder and config
    builder = BundleBuilder(template_dir=template_dir, server_dir=server_dir)
    config = BundleConfig(
        tenant_id=tenant_id,
        api_key=api_key,
        display_name=display_name
    )

    # Build to temp file and read bytes
    with tempfile.NamedTemporaryFile(suffix='.mcpb', delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = builder.build(config=config, output_path=tmp_path)
        if not result.success:
            raise RuntimeError(f"Bundle generation failed: {result.error}")

        # Read the generated bundle
        with open(tmp_path, 'rb') as f:
            return f.read()
    finally:
        # Clean up temp file
        if tmp_path.exists():
            tmp_path.unlink()
