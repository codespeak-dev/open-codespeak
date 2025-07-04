import json
import sys
from pathlib import Path
import argparse
from typing import Any


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


def get_shape(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: get_shape(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [get_shape(item) for item in obj]
    elif isinstance(obj, str):
        return ""
    elif isinstance(obj, int):
        return 0
    elif isinstance(obj, float):
        return 0.0
    elif isinstance(obj, bool):
        return False
    else:
        return None


def find_key_file(cache_dir, hash):
    cache_file = cache_dir / f"{hash}.src.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    else:
        cache_file = cache_dir / f"{hash}.src.txt"
        if cache_file.exists():
            return cache_file.read_text()
        
    # find a ".src.*" file with the name starting with the hash (the actual filename is longer)
    for file in cache_dir.iterdir():
        if file.is_file() and file.name.startswith(hash):
            return find_key_file(cache_dir, file.name.split(".")[0])

    raise ValueError(f"No cache key file found for hash: {hash}")


def near_misses(cache_dir: Path, subj_hash: str):    
    obj = find_key_file(cache_dir, subj_hash)
    subj_shape = get_shape(obj)
    subj_shape_str = json.dumps(subj_shape)
    
    print(f"Searching for similar files to {subj_hash} in {cache_dir}")
    near_misses = []

    for file in cache_dir.iterdir():
        if file.is_file():
            if file.name.startswith(subj_hash):
                continue
            if not file.name.endswith(".src.json"):
                continue
            
            obj = json.loads(file.read_text())
            shape = get_shape(obj)
            if json.dumps(shape) == subj_shape_str:
                near_misses.append(file.name)
    
    for near_miss in near_misses:
        print(near_miss)
    print(f"Found {len(near_misses)} near miss(es)")


def main():
    parser = argparse.ArgumentParser(description="Cache management CLI")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete cache files containing a substring')
    delete_parser.add_argument("substring", help="Substring to search for in files")
    delete_parser.add_argument("--cache-dir", default="test_outputs/.llm_cache", help="Path to cache directory (default: test_outputs/.llm_cache)")
    delete_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    
    # Near miss command
    near_miss_parser = subparsers.add_parser('near_miss', help='Find cache entries with similar structure to a given hash')
    near_miss_parser.add_argument("hash", help="Hash to search for near misses")
    near_miss_parser.add_argument("--cache-dir", default="test_outputs/.llm_cache", help="Path to cache directory (default: test_outputs/.llm_cache)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    cache_dir = Path(args.cache_dir or "test_outputs/.llm_cache")
    
    if not cache_dir.exists():
        print(f"Error: Cache directory does not exist: {cache_dir}")
        sys.exit(1)
    
    if not cache_dir.is_dir():
        print(f"Error: Path is not a directory: {cache_dir}")
        sys.exit(1)

    try:
        if args.command == 'delete':
            deleted_count = clean_cache(cache_dir, args.substring, args.dry_run)
            sys.exit(0)
        elif args.command == 'near_miss':
            near_misses(cache_dir, args.hash)
            sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
