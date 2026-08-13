document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("searchInput");
    const suggestionsList = document.getElementById("suggestionsList");
    const emptyState = document.getElementById("emptyState");
    const loadingSpinner = document.getElementById("loadingSpinner");
    const resultCount = document.getElementById("resultCount");
    const countText = document.getElementById("countText");
    const hintText = document.getElementById("hintText");

    let currentFocus = -1;
    let debounceTimer = null;
    let lastQuery = "";

    // Initialize
    showEmptyState();
    updateKeyboardHint();

    // Event Listeners
    searchInput.addEventListener("input", (e) => {
        const query = e.target.value.trim();
        lastQuery = query;
        clearTimeout(debounceTimer);

        resultCount.classList.add("hidden");

        if (query.length === 0) {
            clearSuggestions();
            showEmptyState();
            return;
        }

        emptyState.classList.add("hidden");
        loadingSpinner.classList.remove("hidden");

        // Debounce network requests by 300ms
        debounceTimer = setTimeout(() => {
            fetchSuggestions(query);
        }, 300);
    });

    // Keyboard Navigation
    searchInput.addEventListener("keydown", (e) => {
        const items = suggestionsList.querySelectorAll(".suggestion-item");
        
        if (items.length === 0) return;

        switch (e.key) {
            case "ArrowDown":
                e.preventDefault();
                currentFocus++;
                setActive(items);
                break;
            case "ArrowUp":
                e.preventDefault();
                currentFocus--;
                setActive(items);
                break;
            case "Enter":
                e.preventDefault();
                if (currentFocus > -1 && items[currentFocus]) {
                    items[currentFocus].click();
                } else if (items.length > 0) {
                    items[0].click();
                }
                break;
            case "Escape":
                clearSuggestions();
                showEmptyState();
                break;
        }
    });

    // Empty State Pill Buttons
    document.querySelectorAll(".pill").forEach((pill) => {
        pill.addEventListener("click", () => {
            const searchTerm = pill.dataset.search;
            searchInput.value = searchTerm;
            searchInput.dispatchEvent(new Event("input", { bubbles: true }));
            searchInput.focus();
        });
    });

    // Fetch Suggestions
    async function fetchSuggestions(query) {
        try {
            const response = await fetch(`/search?q=${encodeURIComponent(query)}&limit=8`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            loadingSpinner.classList.add("hidden");
            renderSuggestions(data, query);
        } catch (error) {
            console.error("Error fetching suggestions:", error);
            loadingSpinner.classList.add("hidden");
            showErrorState();
        }
    }

    // Render Suggestions with Badges
    function renderSuggestions(data, query) {
        suggestionsList.innerHTML = "";
        currentFocus = -1;

        if (!data || data.length === 0) {
            suggestionsList.innerHTML = `
                <li class="no-result">
                    <div>No results found for "${escapeHtml(query)}"</div>
                    <div style="font-size: 0.8rem; margin-top: 4px; color: var(--text-tertiary);">Try different keywords or browse categories</div>
                </li>
            `;
            suggestionsList.classList.remove("hidden");
            resultCount.classList.add("hidden");
            return;
        }

        // Show result count
        countText.textContent = `${data.length} result${data.length > 1 ? "s" : ""} found`;
        resultCount.classList.remove("hidden");

        data.forEach((item) => {
            const li = document.createElement("li");
            li.className = "suggestion-item";
            li.role = "option";
            li.tabIndex = -1;

            const primaryText = highlightText(item.productName, query);
            
            // Build secondary line with badges
            let secondaryHtml = "";
            
            // Brand badge
            if (item.brandName) {
                secondaryHtml += `
                    <span class="badge badge-primary">
                        <svg class="badge-icon" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z"/>
                        </svg>
                        ${escapeHtml(item.brandName)}
                    </span>
                `;
            }

            // Category badge
            if (item.categoryName) {
                secondaryHtml += `
                    <span class="badge badge-accent">
                        <svg class="badge-icon" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L2 7v10c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-10-5z"/>
                        </svg>
                        ${escapeHtml(item.categoryName)}
                    </span>
                `;
            }

            // Specs (highlighted)
            if (item.productSpecification) {
                const specHighlight = highlightText(item.productSpecification, query);
                secondaryHtml += `<span>${specHighlight}</span>`;
            }

            li.innerHTML = `
                <div class="suggestion-content">
                    <div class="primary-line">${primaryText}</div>
                    <div class="secondary-line">${secondaryHtml}</div>
                </div>
            `;

            li.addEventListener("click", () => {
                selectSuggestion(item);
            });

            li.addEventListener("focus", () => {
                currentFocus = Array.from(suggestionsList.querySelectorAll(".suggestion-item")).indexOf(li);
            });

            suggestionsList.appendChild(li);
        });

        suggestionsList.classList.remove("hidden");
    }

    // Select Suggestion
    function selectSuggestion(item) {
        searchInput.value = item.productName;
        clearSuggestions();
        
        // Optional: dispatch custom event for tracking
        document.dispatchEvent(new CustomEvent("materialSelected", { detail: item }));
    }

    // Active State Management
    function setActive(items) {
        removeActive(items);
        
        if (currentFocus >= items.length) currentFocus = 0;
        if (currentFocus < 0) currentFocus = items.length - 1;
        
        items[currentFocus].classList.add("active");
        items[currentFocus].scrollIntoView({ block: "nearest" });
    }

    function removeActive(items) {
        items.forEach((item) => {
            item.classList.remove("active");
        });
    }

    // Clear Suggestions
    function clearSuggestions() {
        suggestionsList.innerHTML = "";
        suggestionsList.classList.add("hidden");
        resultCount.classList.add("hidden");
        currentFocus = -1;
    }

    // Show Empty State
    function showEmptyState() {
        emptyState.classList.remove("hidden");
        suggestionsList.classList.add("hidden");
        resultCount.classList.add("hidden");
    }

    // Show Error State
    function showErrorState() {
        suggestionsList.innerHTML = `
            <li class="no-result">
                <div>⚠️ Unable to fetch results</div>
                <div style="font-size: 0.8rem; margin-top: 4px; color: var(--text-tertiary);">Please try again</div>
            </li>
        `;
        suggestionsList.classList.remove("hidden");
    }

    // Keyboard Hint
    function updateKeyboardHint() {
        if (/Mac|iPhone|iPad|iPod/.test(navigator.platform)) {
            hintText.textContent = "⌘K";
        } else {
            hintText.textContent = "Ctrl+K";
        }
    }

    // Text Highlight with Query
    function highlightText(text, query) {
        if (!text || !query) return escapeHtml(text || "");
        const escaped = escapeHtml(text);
        const regex = new RegExp(`(${escapeRegex(query)})`, "gi");
        return escaped.replace(regex, `<span class="highlight">$1</span>`);
    }

    // HTML Escape
    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Regex Escape
    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    // Click Outside to Close
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".search-wrapper")) {
            clearSuggestions();
            if (!lastQuery) {
                showEmptyState();
            }
        }
    });

    // Focus on search with keyboard shortcut
    document.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "k") {
            e.preventDefault();
            searchInput.focus();
        }
    });
});
