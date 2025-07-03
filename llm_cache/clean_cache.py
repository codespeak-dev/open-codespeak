"""
- find files in the cache directory that contain a given substring
- extract hashes from their names (the part before first dot)
- delete all files in the cache dir whose names start with any of the hashes
"""

import os
import sys
from pathlib import Path
import argparse


def find_files_with_substring(cache_dir: Path, substring: str) -> list[str]:
    """Find all files in cache directory that contain the given substring."""
    matching_files = []
    
    if not cache_dir.exists():
        return matching_files
    
    for file_path in cache_dir.iterdir():
        if file_path.is_file():
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                if substring in content:
                    matching_files.append(file_path.name)
            except Exception:
                # Skip files that can't be read
                continue
    
    return matching_files


def extract_hashes_from_filenames(filenames: list[str]) -> set[str]:
    """Extract hashes from filenames (part before first dot)."""
    hashes = set()
    
    for filename in filenames:
        # Get the part before the first dot
        hash_part = filename.split('.')[0]
        if hash_part:
            hashes.add(hash_part)
    
    return hashes


def delete_files_with_hashes(cache_dir: Path, hashes: set[str], dry_run: bool = False) -> int:
    """Delete all files in cache directory whose names start with any of the given hashes."""
    deleted_count = 0
    
    if not cache_dir.exists():
        return deleted_count
    
    for file_path in cache_dir.iterdir():
        if file_path.is_file():
            filename = file_path.name
            
            # Check if filename starts with any of the hashes
            for hash_prefix in hashes:
                if filename.startswith(hash_prefix):
                    if dry_run:
                        print(f"Would delete: {file_path}")
                    else:
                        try:
                            file_path.unlink()
                            print(f"Deleted: {file_path}")
                        except Exception as e:
                            print(f"Error deleting {file_path}: {e}")
                    deleted_count += 1
                    break  # Don't check other hashes for this file
    
    return deleted_count


def clean_cache(cache_dir: Path, substring: str, dry_run: bool = False) -> int:
    """Main function to clean cache based on substring."""
    print(f"Searching for files containing substring: '{substring}'")
    print(f"Cache directory: {cache_dir}")
    
    # Find files containing the substring
    matching_files = find_files_with_substring(cache_dir, substring)
    print(f"Found {len(matching_files)} files containing the substring")
    
    if not matching_files:
        print("No files found containing the substring")
        return 0
    
    # Extract hashes from matching filenames
    hashes = extract_hashes_from_filenames(matching_files)
    print(f"Extracted {len(hashes)} unique hashes: {sorted(list(hashes))}")
    
    # Delete files with those hashes
    if dry_run:
        print("\nDRY RUN - No files will be deleted:")
    else:
        print("\nDeleting files:")
    
    deleted_count = delete_files_with_hashes(cache_dir, hashes, dry_run)
    
    if dry_run:
        print(f"\nWould delete {deleted_count} files")
    else:
        print(f"\nDeleted {deleted_count} files")
    
    return deleted_count


def main():
    parser = argparse.ArgumentParser(description="Clean cache files containing a substring")
    parser.add_argument("cache_dir", help="Path to cache directory")
    parser.add_argument("substring", help="Substring to search for in files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    
    args = parser.parse_args()
    
    cache_dir = Path(args.cache_dir)
    
    if not cache_dir.exists():
        print(f"Error: Cache directory does not exist: {cache_dir}")
        sys.exit(1)
    
    if not cache_dir.is_dir():
        print(f"Error: Path is not a directory: {cache_dir}")
        sys.exit(1)
    
    try:
        deleted_count = clean_cache(cache_dir, args.substring, args.dry_run)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
