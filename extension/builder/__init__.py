"""
Boswell MCPB Extension Builder

Generates personalized .mcpb bundles for Boswell SaaS users.
"""

__version__ = "0.1.0"

from .bundler import BundleBuilder
from .cli import main as cli_main

__all__ = ["BundleBuilder", "cli_main"]
