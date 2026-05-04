/**
 * app.js — Firmable company search
 *
 * Reads filter values directly from the form DOM on submission.
 * Triggers on: Enter key in the query input, or Apply Filters button click.
 * Renders result cards into #result-list and updates #result-count.
 */

(function () {
  "use strict";

  const SEARCH_URL = "/search";

  // ── DOM refs ──────────────────────────────────────────────
  const form        = document.getElementById("search-form");
  const searchBtn   = document.getElementById("search-btn");
  const clearBtn    = document.getElementById("clear-btn");
  const queryInput  = document.getElementById("query-input");
  const resultList  = document.getElementById("result-list");
  const resultCount = document.getElementById("result-count");
  const loading     = document.getElementById("loading-indicator");
  const errorBox    = document.getElementById("error-message");

  // ── Search trigger: form submit (Enter or Apply Filters) ──
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    runSearch();
  });

  // ── Clear All ─────────────────────────────────────────────
  clearBtn.addEventListener("click", function () {
    form.reset();
    resultList.innerHTML = emptyStateHTML("Enter a query or select filters, then press Enter or Apply Filters.", "Results will appear here.");
    resultCount.textContent = "";
    hideError();
  });

  // ── Core search ───────────────────────────────────────────
  function runSearch() {
    var body = buildRequestBody();
    showLoading();
    hideError();

    fetch(SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            throw new Error(data.detail || ("Request failed: " + res.status));
          });
        }
        return res.json();
      })
      .then(function (data) {
        hideLoading();
        renderResults(data);
      })
      .catch(function (err) {
        hideLoading();
        showError("Search failed: " + (err.message || "unexpected error. Please try again."));
        resultList.innerHTML = "";
        resultCount.textContent = "";
      });
  }

  // ── Build POST body from form ─────────────────────────────
  function buildRequestBody() {
    var body = {};

    var query = queryInput.value.trim();
    if (query) body.query = query;

    var industries = checkedValues("industry");
    if (industries.length) body.industry = industries;

    var sizes = checkedValues("size_range");
    if (sizes.length) body.size_range = sizes;

    var country = val("country");
    if (country) body.country = country;

    var city = val("city");
    if (city) body.city = city;

    var yearFrom = intVal("year_founded_gte");
    if (yearFrom !== null) body.year_founded_gte = yearFrom;

    var yearTo = intVal("year_founded_lte");
    if (yearTo !== null) body.year_founded_lte = yearTo;

    return body;
  }

  // ── Render ────────────────────────────────────────────────
  function renderResults(data) {
    var items = data.items || [];
    var total = typeof data.total === "number" ? data.total : items.length;

    resultCount.textContent = total.toLocaleString() + " result" + (total !== 1 ? "s" : "") + " found";

    if (!items.length) {
      resultList.innerHTML = emptyStateHTML(
        "No companies matched your search.",
        "Try adjusting your filters."
      );
      return;
    }

    resultList.innerHTML = items.map(cardHTML).join("");
  }

  function cardHTML(c) {
    var lines = [];

    lines.push('<div class="company-card">');
    lines.push('  <div class="card-name">' + esc(c.name) + '</div>');

    if (c.domain) {
      lines.push('  <div class="card-domain">' + esc(c.domain) + '</div>');
    }

    lines.push('  <div class="card-meta">');

    if (c.industry) {
      lines.push('    <span><strong>Industry</strong> ' + esc(c.industry) + '</span>');
    }

    var location = buildLocation(c.city, c.region, c.country);
    if (location) {
      lines.push('    <span><strong>Location</strong> ' + esc(location) + '</span>');
    }

    if (c.year_founded) {
      lines.push('    <span><strong>Founded</strong> ' + esc(String(c.year_founded)) + '</span>');
    }

    if (c.size_range) {
      lines.push('    <span><strong>Size</strong> ' + esc(c.size_range) + '</span>');
    }

    if (typeof c.current_employee_estimate === "number") {
      lines.push('    <span><strong>Employees</strong> ' + c.current_employee_estimate.toLocaleString() + '</span>');
    }

    lines.push('  </div>');
    lines.push('</div>');

    return lines.join("\n");
  }

  function buildLocation(city, region, country) {
    return [city, region, country].filter(Boolean).join(", ");
  }

  // ── State helpers ─────────────────────────────────────────
  function showLoading() {
    loading.style.display = "inline";
    searchBtn.disabled = true;
  }

  function hideLoading() {
    loading.style.display = "none";
    searchBtn.disabled = false;
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.style.display = "block";
  }

  function hideError() {
    errorBox.style.display = "none";
    errorBox.textContent = "";
  }

  function emptyStateHTML(heading, sub) {
    return (
      '<div class="empty-state"><strong>' +
      esc(heading) +
      "</strong><p>" +
      esc(sub) +
      "</p></div>"
    );
  }

  // ── DOM helpers ───────────────────────────────────────────
  function checkedValues(name) {
    return Array.from(form.querySelectorAll('input[name="' + name + '"]:checked')).map(function (el) {
      return el.value;
    });
  }

  function val(name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? el.value.trim() : "";
  }

  function intVal(name) {
    var el = form.querySelector('[name="' + name + '"]');
    if (!el || el.value.trim() === "") return null;
    var n = parseInt(el.value, 10);
    return isNaN(n) ? null : n;
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
