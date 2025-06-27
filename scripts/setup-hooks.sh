#!/bin/bash

# Setup script to install git hooks for all team members
# Run this once after cloning the repository

echo "Setting up git hooks for the team..."

# Check if .githooks directory exists
if [ ! -d ".githooks" ]; then
    echo "Error: .githooks directory not found"
    exit 1
fi

# Configure git to use our shared hooks directory
git config core.hooksPath .githooks

# Make hooks executable
chmod +x .githooks/*

# Verify setup
if [ -f ".githooks/pre-commit" ]; then
    echo "✅ Pre-commit hook installed successfully"
    echo "   - Automatically cleans empty lines with tabs from Python files"
    echo "   - Runs before every commit"
else
    echo "❌ Pre-commit hook not found"
    exit 1
fi

echo ""
echo "🎉 Git hooks setup complete!"
echo ""
echo "The pre-commit hook will now:"
echo "  • Clean empty lines with tabs from Python files"
echo "  • Run automatically on every commit"
echo "  • Keep the codebase consistent across the team"
echo ""
echo "To manually clean files, run: python scripts/clean_whitespace.py"
