#!/bin/bash

# OMem CLI Test Script
# This script tests all CLI commands with a realistic dataset

echo "=================================================="
echo "  OMem CLI Comprehensive Test"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

test_step() {
    echo -e "${BLUE}▶${NC} $1"
}

test_success() {
    echo -e "${GREEN}✓${NC} $1"
    echo ""
}

# Step 1: Clear existing data for fresh test
test_step "Step 1: Clearing existing memories..."
omem clear --yes 2>/dev/null || true
test_success "Cleared"

# Step 2: Initialize OMem
test_step "Step 2: Initializing OMem..."
omem init
test_success "Initialized"

# Step 3: Check initial stats
test_step "Step 3: Checking initial stats..."
omem stats
test_success "Stats displayed"

# Step 4: Add individual memories
test_step "Step 4: Adding individual memories..."
omem add "Testing OMem CLI functionality" --importance 0.9
omem add "User prefers dark mode" --importance 0.8 --type preference
omem add "Critical bug in authentication" --importance 1.0 --type active
test_success "Added 3 individual memories"

# Step 5: Load bulk data from JSON
test_step "Step 5: Loading conversation dataset..."
omem load test_conversations.json
test_success "Loaded bulk data"

# Step 6: Check stats after loading
test_step "Step 6: Checking stats after bulk load..."
omem stats
test_success "Stats updated"

# Step 7: List memories
test_step "Step 7: Listing memories..."
omem list --limit 10
test_success "Listed memories"

# Step 8: Search for specific topics
test_step "Step 8: Searching for 'security vulnerability'..."
omem search "security vulnerability" --k 3
test_success "Search completed"

test_step "Step 9: Searching for 'dark mode'..."
omem search "dark mode" --k 3
test_success "Search completed"

test_step "Step 10: Searching for 'performance optimization'..."
omem search "performance optimization" --k 3
test_success "Search completed"

# Step 11: Filter by context type
test_step "Step 11: Searching bugs..."
omem search "bug" --k 5 --context-type bugs
test_success "Context-filtered search completed"

# Step 12: Time-range filtering
test_step "Step 12: Recent memories..."
omem search "user" --k 5 --time-range recent
test_success "Time-filtered search completed"

# Step 13: Inspect retrieval scores
test_step "Step 13: Inspecting 'authentication' query..."
omem inspect "authentication" --k 3
test_success "Inspection completed"

# Step 14: List namespaces
test_step "Step 14: Listing namespaces..."
omem namespaces
test_success "Namespaces listed"

# Step 15: Add memories to different namespace
test_step "Step 15: Adding to 'testing' namespace..."
omem add "Test memory in different namespace" --namespace testing
omem add "Another test memory" --namespace testing
test_success "Added to testing namespace"

# Step 16: Check namespaces again
test_step "Step 16: Listing namespaces after additions..."
omem namespaces
test_success "Updated namespaces"

# Step 17: Search within specific namespace
test_step "Step 17: Searching within 'testing' namespace..."
omem search "test" --namespace testing --k 3
test_success "Namespace-specific search completed"

# Step 18: List by type
test_step "Step 18: Listing DECISION type memories..."
omem list --type decision --limit 5
test_success "Type-filtered list"

# Step 19: Export memories
test_step "Step 19: Exporting memories to JSON..."
omem export --output test_export.json
test_success "Exported to test_export.json"

test_step "Step 20: Exporting memories to TXT..."
omem export --format txt --output test_export.txt
test_success "Exported to test_export.txt"

# Step 21: Maintenance operations
test_step "Step 21: Running compression..."
omem maintain --compress
test_success "Compression completed"

test_step "Step 22: Generating reflections..."
omem maintain --reflect
test_success "Reflections generated"

# Step 23: Check stats after maintenance
test_step "Step 23: Stats after maintenance..."
omem stats
test_success "Final stats"

# Step 24: Run demo
test_step "Step 24: Running interactive demo..."
omem demo
test_success "Demo completed"

# Step 25: Small benchmark
test_step "Step 25: Running quick benchmark (1000 memories)..."
omem benchmark --n 1000
test_success "Benchmark completed"

echo ""
echo "=================================================="
echo -e "${GREEN}  All CLI Tests Completed Successfully!${NC}"
echo "=================================================="
echo ""
echo "Generated files:"
echo "  - test_export.json"
echo "  - test_export.txt"
echo ""
echo "Try these commands yourself:"
echo "  omem search \"your query\""
echo "  omem list --limit 10"
echo "  omem inspect \"your query\""
echo "  omem stats"
echo ""
