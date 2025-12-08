#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0",
#     "click>=8.0",
# ]
# ///
"""Generate redirect files from Jupyter Book v1 URLs to MyST/JB2 URLs.

Reads a MyST table of contents and creates HTML redirect pages that map
old .html URLs to new directory-based URLs.

Usage:
    uv run generate_redirects.py --base-url https://example.com/

Inspired by Silas Santini's work in the data-8/textbook repository.
"""
import re
import sys
from pathlib import Path
from typing import List, Dict, Any

import yaml
import click


def flatten_toc(toc: List[Dict[str, Any]]) -> List[str]:
    """Recursively extract all file paths from the table of contents.

    Args:
        toc: The table of contents structure from myst.yml

    Returns:
        A flat list of all file paths referenced in the TOC
    """
    files = []
    for item in toc:
        if 'file' in item:
            files.append(item['file'])
        if 'children' in item:
            files.extend(flatten_toc(item['children']))
    return files


def sanitize_for_myst_url(path: str) -> str:
    """Sanitize a file path to match MyST's URL slug format.

    MyST applies these transformations when converting file paths to URLs:
    1. Lowercase the entire path
    2. Replace spaces and underscores with hyphens
    3. Collapse multiple consecutive hyphens into a single hyphen
    4. Strip leading and trailing hyphens from each path component

    Args:
        path: The file path to sanitize (with or without extension)

    Returns:
        The sanitized URL slug matching MyST's behavior

    Examples:
        >>> sanitize_for_myst_url("Test With Spaces")
        'test-with-spaces'
        >>> sanitize_for_myst_url("TestMixedCase")
        'testmixedcase'
        >>> sanitize_for_myst_url("test_with_underscores")
        'test-with-underscores'
        >>> sanitize_for_myst_url("_LeadingUnderscore")
        'leadingunderscore'
        >>> sanitize_for_myst_url("Multiple___Special")
        'multiple-special'
        >>> sanitize_for_myst_url("charters/MediaStrategyCharter")
        'charters/mediastrategycharter'
        >>> sanitize_for_myst_url("content/01-demand/01-demand")
        'content/demand/demand'
    """
    # Convert to lowercase
    slug = path.lower()

    # Replace spaces and underscores with hyphens
    slug = slug.replace(' ', '-').replace('_', '-')

    # Collapse multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading numbers and hyphens
    slug = "/".join([re.sub(r'^[\d-]+', '', s) for s in slug.split('/')])

    # Strip leading/trailing hyphens from each path component
    # This preserves directory structure while cleaning each component
    parts = slug.split('/')
    parts = [part.strip('-') for part in parts]
    slug = '/'.join(parts)

    return slug


def create_redirect_html(old_slug: str, new_url: str, output_root: Path) -> Path:
    """Create an HTML redirect file with meta refresh tag.

    Args:
        old_slug: The old URL path (e.g., 'overview.html')
        new_url: The new URL to redirect to (e.g., 'https://example.com/overview/')
        output_root: The root directory where redirect files should be created

    Returns:
        Path to the created redirect file
    """
    # Ensure the output directory exists
    output_file = output_root / old_slug
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write a simple HTML redirect
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url={new_url}">
    <meta charset="utf-8">
    <title>Redirecting...</title>
</head>
<body>
    <p>This page has moved. Redirecting to <a href="{new_url}">{new_url}</a></p>
</body>
</html>
"""
    output_file.write_text(html)
    return output_file


def load_myst_toc(myst_config_path: Path) -> List[str]:
    """Load and extract file paths from a MyST configuration file.

    Args:
        myst_config_path: Path to the myst.yml configuration file

    Returns:
        List of file paths from the table of contents

    Raises:
        FileNotFoundError: If the config file doesn't exist
        KeyError: If the config file doesn't have the expected structure
    """
    if not myst_config_path.exists():
        raise FileNotFoundError(f"MyST config file not found: {myst_config_path}")

    with open(myst_config_path) as f:
        config = yaml.safe_load(f)

    if 'project' not in config or 'toc' not in config['project']:
        raise KeyError("MyST config must have 'project.toc' structure")

    return flatten_toc(config['project']['toc'])


def discover_myst_config() -> Path:
    """Auto-discover myst.yml in common locations.

    Returns:
        Path to myst.yml

    Raises:
        FileNotFoundError: If myst.yml not found in any common location
    """
    common_locations = [
        Path('./myst.yml'),
        Path('./docs/myst.yml'),
    ]

    for location in common_locations:
        if location.exists():
            return location

    raise FileNotFoundError(
        "Could not find myst.yml in common locations (./myst.yml, ./docs/myst.yml). "
        "Use --myst-config to specify the path explicitly."
    )


def generate_redirects(
    base_url: str,
    output_root: Path,
    myst_config_path: Path,
) -> int:
    """Generate redirect files based on MyST configuration."""
    # Ensure base_url ends with /
    if not base_url.endswith('/'):
        base_url += '/'

    # Load file paths from MyST TOC
    file_paths = load_myst_toc(myst_config_path)

    if not file_paths:
        click.echo("No files found in TOC", err=True)
        return 0

    # Auto-detect index file: the first file in the TOC is the landing page
    index_file_path = file_paths[0]
    index_slug = sanitize_for_myst_url(
        index_file_path.replace('.md', '').replace('.ipynb', '')
    )

    # Generate redirects for each file
    count = 0
    for file_path in file_paths:
        # Old URL: path/to/file.md -> path/to/file.html
        old_slug = file_path.replace('.md', '.html').replace('.ipynb', '.html')

        # New URL: path/to/file.md -> /path/to/file/
        path_without_ext = file_path.replace('.md', '').replace('.ipynb', '')
        new_slug = sanitize_for_myst_url(path_without_ext)

        # The first file in the TOC becomes the root index
        new_url = base_url if new_slug == index_slug else base_url + new_slug + '/'

        create_redirect_html(old_slug, new_url, output_root)
        click.echo(f"{old_slug} -> {new_url}")
        count += 1

    return count


@click.command()
@click.option(
    '--base-url',
    required=True,
    help='Base URL of the website (e.g., https://jupyter.org/governance/)',
)
@click.option(
    '--output-dir',
    type=click.Path(path_type=Path),
    default='_build/html',
    help='Directory where redirect files will be created (default: _build/html)',
)
@click.option(
    '--myst-config',
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help='Path to the myst.yml configuration file (default: auto-discover)',
)
def main(base_url: str, output_dir: Path, myst_config: Path):
    """Generate HTML redirect files for Jupyter Book v1 to MyST migration."""
    # Auto-discover config if not specified
    if myst_config is None:
        try:
            myst_config = discover_myst_config()
            click.echo(f"Using config: {myst_config}")
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    try:
        count = generate_redirects(
            base_url=base_url,
            output_root=output_dir,
            myst_config_path=myst_config,
        )

        click.echo(f"\nGenerated {count} redirect files in {output_dir}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Make sure your myst.yml has a 'project.toc' structure", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
