// static/js/app.js
//
// Small bits of interactivity that don't need a server round-trip.

document.addEventListener("DOMContentLoaded", function () {
  // Password "Show"/"Hide" toggle buttons - each one has data-target="<input id>"
  document.querySelectorAll(".toggle-password").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.dataset.target);
      if (!input) return;
      var isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      btn.textContent = isHidden ? "Hide" : "Show";
    });
  });

  // Forms with class="confirm-delete" show a native confirm() dialog before
  // submitting - used for the Delete button on the My Projects page so a stray click
  // can't wipe out a project. data-confirm on the form supplies the message.
  document.querySelectorAll(".confirm-delete").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var message = form.dataset.confirm || "Are you sure?";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  // Generic show/hide toggle - clicking a button with class="toggle-target" flips
  // the `hidden` attribute on every id listed (space-separated) in
  // data-toggle-target. Used for the Notes section's "+ Add Note" compose panel and
  // each note's Edit/Cancel switch between its view and edit blocks - since Edit and
  // Cancel both target the exact same pair of ids, one flip-both handler covers
  // opening AND closing without needing separate "open" and "close" logic.
  document.querySelectorAll(".toggle-target").forEach(function (btn) {
    btn.addEventListener("click", function () {
      (btn.dataset.toggleTarget || "").split(/\s+/).filter(Boolean).forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.hidden = !el.hidden;
      });
    });
  });

  // Auto-dismiss flash messages after a few seconds
  document.querySelectorAll(".flash").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.4s ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 400);
    }, 4000);
  });

  // Buttons that trigger a live, ChatGPT-style "typing" AI generation (the AI
  // Summary / Relevance Analysis buttons on paper_detail.html and
  // project_paper_detail.html). Each button carries:
  //   data-stream-url - the POST endpoint that streams back newline-delimited JSON
  //                      (NDJSON): one JSON object per line, each either
  //                      {"delta": "..."}, {"error": "..."}, or
  //                      {"done": true, "text": "..."} - see
  //                      routes/papers_routes.py's summarize_stream() /
  //                      generate_relevance_stream() for exactly what it sends.
  //   data-target      - the id of the <div> whose contents this replaces with the
  //                      streamed text as it arrives. Mutually exclusive with
  //                      data-targets below - each button uses exactly one.
  //   data-paragraphs  - "true" on the AI Summary button only. The summary is
  //                      generated as six blank-line-separated paragraphs (see
  //                      services/openai_service.py's stream_summarize_paper()), so
  //                      this renders each one as its own justified <p class=
  //                      "ai-summary-paragraph"> as it streams in, matching how
  //                      paper.summary is split back apart on page load in the
  //                      templates. Relevance Analysis omits this attribute and
  //                      keeps rendering as a single paragraph.
  //   data-targets     - space-separated element ids, used by the Literature Matrix's
  //                      "Extract with AI" button instead of data-target. The stream
  //                      still carries one blank-line-separated block of text (see
  //                      services/openai_service.py's stream_extract_matrix_fields()),
  //                      but here each of its paragraphs is routed to its own target
  //                      id in order (Methodology/Sample/Findings/Limitations -> that
  //                      row's four table cells) instead of all landing in one place.
  // A plain fetch() + manual stream reader is used here (rather than EventSource/SSE)
  // because EventSource only supports GET requests, and every mutating action in this
  // app goes through POST.
  document.querySelectorAll("[data-stream-url]").forEach(function (button) {
    button.addEventListener("click", function () {
      var targetIds = (button.dataset.targets || "").split(/\s+/).filter(Boolean);
      var multiTarget = targetIds.length > 0;
      var target = multiTarget ? null : document.getElementById(button.dataset.target);
      if (!multiTarget && !target) return;

      var usesParagraphs = button.dataset.paragraphs === "true";
      var originalButtonText = button.textContent;
      button.disabled = true;
      button.textContent = "Generating…";

      var fullText = "";
      var finished = false;

      // Rebuilds the target(s)' contents from fullText every time new text arrives,
      // rather than appending in place - simpler and safer than trying to patch in a
      // new paragraph break that might arrive split across two separate stream events
      // (e.g. one delta ending in "\n" and the next starting with "\n"). The summary
      // (or matrix row) is short enough that re-rendering per chunk is cheap.
      function renderParagraphInto(el, text, showCursor) {
        el.innerHTML = "";
        var p = document.createElement("p");
        p.className = usesParagraphs ? "detail-card-body ai-summary-paragraph" : "detail-card-body";
        p.appendChild(document.createTextNode(text));
        if (showCursor) {
          var cursor = document.createElement("span");
          cursor.className = "typing-cursor";
          p.appendChild(cursor);
        }
        el.appendChild(p);
      }

      function render(showCursor) {
        var paragraphs = (usesParagraphs || multiTarget)
          ? fullText.split(/\n{2,}/).map(function (s) { return s.trim(); }).filter(Boolean)
          : [fullText];
        if (paragraphs.length === 0) paragraphs = [""];

        if (multiTarget) {
          targetIds.forEach(function (id, i) {
            var el = document.getElementById(id);
            if (!el) return;
            renderParagraphInto(el, paragraphs[i] || "", showCursor && i === targetIds.length - 1);
          });
          return;
        }

        target.innerHTML = "";
        paragraphs.forEach(function (text, i) {
          var p = document.createElement("p");
          p.className = usesParagraphs ? "detail-card-body ai-summary-paragraph" : "detail-card-body";
          p.appendChild(document.createTextNode(text));
          if (showCursor && i === paragraphs.length - 1) {
            var cursor = document.createElement("span");
            cursor.className = "typing-cursor";
            p.appendChild(cursor);
          }
          target.appendChild(p);
        });
      }

      render(true); // shows one empty paragraph (or row of them) with a cursor before anything arrives

      function showError(message) {
        if (multiTarget) {
          targetIds.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            el.innerHTML = "";
            var errorParagraph = document.createElement("p");
            errorParagraph.className = "detail-card-empty stream-error";
            errorParagraph.textContent = message;
            el.appendChild(errorParagraph);
          });
          return;
        }
        target.innerHTML = "";
        var errorParagraph = document.createElement("p");
        errorParagraph.className = "detail-card-empty stream-error";
        errorParagraph.textContent = message;
        target.appendChild(errorParagraph);
      }

      function finish(regenerateLabel) {
        button.disabled = false;
        button.textContent = regenerateLabel;
      }

      fetch(button.dataset.streamUrl, { method: "POST" })
        .then(function (response) {
          if (!response.ok || !response.body) {
            throw new Error("The server didn't respond as expected.");
          }

          var reader = response.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";

          function pump() {
            return reader.read().then(function (result) {
              if (result.done) {
                // A stream that ends without ever sending {"done": true} or
                // {"error": ...} (e.g. the connection dropped mid-response) still
                // needs to leave the button usable again rather than stuck on
                // "Generating…" forever.
                if (!finished) {
                  finished = true;
                  finish(originalButtonText);
                }
                return;
              }

              buffer += decoder.decode(result.value, { stream: true });
              var lines = buffer.split("\n");
              buffer = lines.pop(); // last element may be an incomplete line - keep it for next time

              lines.forEach(function (line) {
                if (!line.trim()) return;
                var event;
                try {
                  event = JSON.parse(line);
                } catch (parseError) {
                  return;
                }

                if (event.error) {
                  finished = true;
                  showError(event.error);
                  finish(originalButtonText);
                } else if (event.done) {
                  finished = true;
                  fullText = event.text || fullText;
                  render(false);
                  finish(button.dataset.regenerateLabel || "Regenerate");
                } else if (event.delta) {
                  fullText += event.delta;
                  render(true);
                }
              });

              return pump();
            });
          }

          return pump();
        })
        .catch(function () {
          if (!finished) {
            finished = true;
            showError("Something went wrong generating this - try again.");
            finish(originalButtonText);
          }
        });
    });
  });

  // Instant client-side search filter for the "My Papers" and a project's "Saved
  // Papers" lists - filters the already-rendered list by title/authors as you type,
  // with no server round-trip (my_papers.html / project_papers.html). Each input
  // carries:
  //   data-filter-target - id of the container whose direct .result-card children
  //                         get shown/hidden as you type
  //   data-filter-empty  - id of the "no results" message to show only when the
  //                         search has hidden every card
  // Matching is against each .result-card's own data-search-text attribute (a
  // lowercased "title authors" string set in the template), not its visible text -
  // so badges like "Semantic Scholar" or "Uploaded PDF" never accidentally match.
  document.querySelectorAll("[data-filter-target]").forEach(function (input) {
    var container = document.getElementById(input.dataset.filterTarget);
    if (!container) return;
    var emptyMessage = document.getElementById(input.dataset.filterEmpty);
    var cards = Array.prototype.slice.call(container.querySelectorAll(".result-card"));

    input.addEventListener("input", function () {
      var query = input.value.trim().toLowerCase();
      var visibleCount = 0;
      cards.forEach(function (card) {
        var matches = !query || (card.dataset.searchText || "").indexOf(query) !== -1;
        card.hidden = !matches;
        if (matches) visibleCount++;
      });
      if (emptyMessage) emptyMessage.hidden = visibleCount !== 0;
    });
  });
});
