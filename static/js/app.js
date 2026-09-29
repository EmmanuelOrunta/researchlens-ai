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

      // Paper Synthesis's "Generate Synthesis" button (paper_synthesis.html) is the
      // one stream trigger whose input isn't fixed by its URL - which papers to
      // synthesize is a fresh choice every time, read here from whichever checkboxes
      // sharing data-paper-checkbox-name's name are currently checked, and sent as the
      // POST body. Every other [data-stream-url] button omits this attribute, so
      // requestBody stays null and fetch() below sends no body, same as before.
      var checkboxName = button.dataset.paperCheckboxName;
      var requestBody = null;
      if (checkboxName) {
        var checkedBoxes = Array.prototype.slice.call(
          document.querySelectorAll('input[type="checkbox"][name="' + checkboxName + '"]:checked')
        );
        var minPapers = Number(button.dataset.minPapers || "0");
        if (checkedBoxes.length < minPapers) {
          window.alert("Select at least " + minPapers + " papers first.");
          return;
        }
        requestBody = new URLSearchParams();
        checkedBoxes.forEach(function (cb) { requestBody.append("paper_ids", cb.value); });
      }

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

      fetch(button.dataset.streamUrl, { method: "POST", body: requestBody })
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

  // Instant client-side sort for the "My Papers" list (my_papers.html) - reorders the
  // already-rendered .result-card elements in the DOM the moment you pick an option,
  // with no server round-trip. Independent of the search filter above (both target
  // the same list container: this reorders cards, the filter shows/hides them - a
  // hidden card just gets reordered along with the rest, still hidden).
  //   data-sort-target - id of the container whose .result-card children get reordered
  // Each .result-card carries its sort keys as data attributes (set in the template):
  //   data-sort-date      - ISO paper.created_at, for "recent" (newest first)
  //   data-sort-title     - lowercased paper.title, for "title" (A-Z)
  //   data-sort-relevance - this paper's best 1-5 AI relevance rating across every
  //                         project it's saved to, or "" if it's never been rated
  //                         anywhere - for "relevance" (highest first, unrated last)
  document.querySelectorAll("[data-sort-target]").forEach(function (select) {
    var container = document.getElementById(select.dataset.sortTarget);
    if (!container) return;

    select.addEventListener("change", function () {
      var cards = Array.prototype.slice.call(container.querySelectorAll(".result-card"));
      var mode = select.value;

      cards.sort(function (a, b) {
        if (mode === "title") {
          return (a.dataset.sortTitle || "").localeCompare(b.dataset.sortTitle || "");
        }
        if (mode === "relevance") {
          var ratingA = a.dataset.sortRelevance === "" ? -1 : Number(a.dataset.sortRelevance);
          var ratingB = b.dataset.sortRelevance === "" ? -1 : Number(b.dataset.sortRelevance);
          return ratingB - ratingA;
        }
        return (b.dataset.sortDate || "").localeCompare(a.dataset.sortDate || ""); // "recent" (default)
      });

      // Re-appending each card in its new sorted order moves the existing element
      // rather than recreating it, so nothing about the card (or its identity) is lost.
      cards.forEach(function (card) { container.appendChild(card); });
    });
  });

  // Generic dropdown menu - e.g. the Literature Matrix's "Export" button, whose menu
  // holds the Excel/PDF/Word download links (literature_matrix.html). A wrapper marked
  // data-dropdown holds one data-dropdown-toggle button and one data-dropdown-menu
  // panel; clicking the button shows/hides the panel, which also closes on choosing a
  // menu item, clicking outside, or pressing Escape - so it never gets left open.
  document.querySelectorAll("[data-dropdown]").forEach(function (wrapper) {
    var toggle = wrapper.querySelector("[data-dropdown-toggle]");
    var menu = wrapper.querySelector("[data-dropdown-menu]");
    if (!toggle || !menu) return;

    function closeMenu() { menu.hidden = true; }

    toggle.addEventListener("click", function (event) {
      event.stopPropagation();
      menu.hidden = !menu.hidden;
    });
    menu.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeMenu);
    });
    document.addEventListener("click", function (event) {
      if (!menu.hidden && !wrapper.contains(event.target)) closeMenu();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeMenu();
    });
  });

  // Generic "select all" checkbox - e.g. Paper Synthesis's paper picker
  // (paper_synthesis.html). A checkbox marked data-select-all="<name>" checks/unchecks
  // every checkbox sharing that name attribute, and reflects their state back (checked
  // only once every box is) both on load - so it starts right if some boxes are
  // already pre-checked, e.g. after a page reload - and as individual boxes change.
  document.querySelectorAll("[data-select-all]").forEach(function (selectAllBox) {
    var targetName = selectAllBox.dataset.selectAll;
    var checkboxes = Array.prototype.slice.call(
      document.querySelectorAll('input[type="checkbox"][name="' + targetName + '"]')
    );
    if (checkboxes.length === 0) return;

    function syncSelectAllState() {
      selectAllBox.checked = checkboxes.every(function (cb) { return cb.checked; });
    }

    selectAllBox.addEventListener("change", function () {
      checkboxes.forEach(function (cb) { cb.checked = selectAllBox.checked; });
    });
    checkboxes.forEach(function (cb) {
      cb.addEventListener("change", syncSelectAllState);
    });
    syncSelectAllState();
  });

  // Generic "Copy" button - the AI Summary (paper_detail.html, project_paper_detail.html)
  // and Paper Synthesis (paper_synthesis.html) each get one of these next to their
  // Regenerate/Generate button. A button marked data-copy-target="<container id>" copies
  // that container's rendered text (paragraph breaks and all) to the clipboard, and
  // briefly relabels itself to confirm it worked - but only if the container actually
  // holds generated text rather than one of its own "Not generated yet."/"Add an API
  // key"/etc. placeholder messages, which always render as a bare <p class="detail-
  // card-empty"> with no sibling - copying those would just put unhelpful boilerplate on
  // the user's clipboard.
  document.querySelectorAll("[data-copy-target]").forEach(function (button) {
    var target = document.getElementById(button.dataset.copyTarget);
    if (!target) return;
    var originalLabel = button.textContent;

    function fallbackCopy(text) {
      var textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      try { document.execCommand("copy"); } catch (copyError) { /* nothing more we can do */ }
      document.body.removeChild(textarea);
    }

    function showCopied() {
      button.textContent = "✓ Copied";
      setTimeout(function () { button.textContent = originalLabel; }, 1500);
    }

    button.addEventListener("click", function () {
      var hasRealContent = !!target.querySelector("p:not(.detail-card-empty)");
      if (!hasRealContent) return;

      var text = (target.innerText || target.textContent || "").trim();
      if (!text) return;

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(showCopied, function () {
          fallbackCopy(text);
          showCopied();
        });
      } else {
        fallbackCopy(text);
        showCopied();
      }
    });
  });

  // "Ask the Literature" chat form (ask_literature.html). Unlike the single-target
  // [data-stream-url] buttons above (AI Summary, Paper Synthesis, etc.), which
  // replace one fixed container's contents every time, a chat conversation APPENDS
  // a new pair of bubbles - the question you just asked, and the AI's streaming
  // answer - to a growing thread each time you ask something, while every earlier
  // turn stays exactly as it was (the full history the page loaded with, plus
  // whatever's been asked so far this visit). A form marked data-chat-form carries:
  //   data-stream-url - the POST endpoint that streams back NDJSON: a leading
  //                      {"question_id": <id>}, then any number of {"delta": "..."},
  //                      then exactly one of {"error": "..."} or
  //                      {"done": true, "text": "...", "answer_id": <id>} - see
  //                      routes/papers_routes.py's ask_literature_stream(). The
  //                      question itself is read from the form's own textarea and
  //                      sent as the POST body (question=...) at submit time,
  //                      rather than being fixed by any data attribute. Editing and
  //                      resending an earlier question (see further down) POSTs
  //                      the same event shapes to a sibling "resend" URL derived
  //                      from this one - see submitEdit() below.
  // Icon markup for the chat thread's hover-reveal actions (edit a question,
  // copy an answer) - inline SVG rather than emoji, to match the ChatGPT/
  // Claude-style icon buttons instead of the app's usual playful emoji glyphs.
  var CHAT_EDIT_ICON = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5Z" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var CHAT_COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M5 15V5a2 2 0 0 1 2-2h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

  document.querySelectorAll("[data-chat-form]").forEach(function (form) {
    var textarea = form.querySelector("textarea");
    var button = form.querySelector("button[type='submit']");
    var thread = document.getElementById("chat-thread");
    if (!textarea || !button || !thread) return;
    var userInitials = thread.dataset.userInitials || "";

    function scrollToBottom() {
      thread.scrollTop = thread.scrollHeight;
    }

    // Splits text into blank-line-separated paragraphs (same convention every AI
    // output in this app follows) and renders them into a message bubble's body,
    // replacing whatever was there before - simpler and safer than patching in a
    // paragraph break that might arrive split across two separate stream events,
    // the same tradeoff the [data-stream-url] handler above makes for the same
    // reason.
    function renderBodyText(body, text, showCursor) {
      body.innerHTML = "";
      var paragraphs = (text || "").split(/\n{2,}/).map(function (s) { return s.trim(); }).filter(Boolean);
      if (paragraphs.length === 0) paragraphs = [""];
      paragraphs.forEach(function (paragraphText, i) {
        var p = document.createElement("p");
        p.appendChild(document.createTextNode(paragraphText));
        if (showCursor && i === paragraphs.length - 1) {
          var cursor = document.createElement("span");
          cursor.className = "typing-cursor";
          p.appendChild(cursor);
        }
        body.appendChild(p);
      });
    }

    // The plain question/answer text a bubble currently shows, reconstructed from
    // its rendered paragraphs (rejoined with blank lines) - what enterEditMode()
    // below pre-fills its textarea with, so editing starts from exactly what the
    // conversation already shows rather than some separately-tracked copy that
    // could drift from it.
    function bubbleText(body) {
      return Array.prototype.slice.call(body.querySelectorAll("p"))
        .map(function (p) { return p.textContent; })
        .join("\n\n");
    }

    // Appends a new row (avatar + bubble, role is "user" or "assistant") to the
    // thread and returns {bubble, body}, so the caller can keep streaming text
    // into the body and later tag the bubble with its database id (see
    // setMessageId() below) - also clears the "Ask your first question..."
    // empty-state message the first time a real turn is added, so it doesn't
    // linger above a non-empty thread. An assistant row gets its "Copy" icon
    // right away (copying doesn't need a database id); a user row's "Edit" icon
    // is added later, once setMessageId() knows the id editing needs.
    function addBubble(role, text) {
      var empty = document.getElementById("chat-empty-message");
      if (empty) empty.remove();

      var row = document.createElement("div");
      row.className = "chat-row chat-row-" + role;

      var avatar = document.createElement("div");
      avatar.className = "chat-avatar chat-avatar-" + role;
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = role === "user" ? userInitials : "✦";
      row.appendChild(avatar);

      var bubble = document.createElement("div");
      bubble.className = "chat-message chat-message-" + role;

      var body = document.createElement("div");
      body.className = "chat-message-body";
      bubble.appendChild(body);

      var actions = document.createElement("div");
      actions.className = "chat-message-actions";
      if (role === "assistant") {
        var copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "chat-icon-btn";
        copyBtn.setAttribute("data-chat-copy-btn", "");
        copyBtn.setAttribute("aria-label", "Copy answer");
        copyBtn.title = "Copy";
        copyBtn.innerHTML = CHAT_COPY_ICON;
        actions.appendChild(copyBtn);
      }
      bubble.appendChild(actions);

      row.appendChild(bubble);
      thread.appendChild(row);
      renderBodyText(body, text, false);
      scrollToBottom();
      return { bubble: bubble, body: body };
    }

    // Tags a bubble with the database id its message just got (from a
    // {"question_id"} or {"done", "answer_id"} event), and - for a user bubble -
    // adds the "Edit" icon button this id makes possible. Bubbles rendered by
    // the template on page load already carry both (see ask_literature.html);
    // this is only needed for a bubble this page just created client-side,
    // which starts out with neither, since the id doesn't exist until the
    // server persists it.
    function setMessageId(bubble, messageId) {
      bubble.dataset.messageId = messageId;
      if (bubble.classList.contains("chat-message-user") && !bubble.querySelector("[data-chat-edit-btn]")) {
        var editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "chat-icon-btn";
        editBtn.setAttribute("data-chat-edit-btn", "");
        editBtn.setAttribute("aria-label", "Edit question");
        editBtn.title = "Edit";
        editBtn.innerHTML = CHAT_EDIT_ICON;
        var actions = bubble.querySelector(".chat-message-actions");
        if (actions) actions.appendChild(editBtn);
      }
    }

    // Disables (or re-enables) every "Edit" icon in the thread, alongside the
    // main composer, while a question or a resend is in flight - editing a second
    // question mid-stream would race against the first one's own truncation logic
    // (see edit_and_truncate_message() in services/literature_chat_service.py),
    // since both would be deleting/appending to the same linear thread at once.
    // The send button also gets a pulsing "busy" look in place of the text-swap
    // this used to do, since it's icon-only now (see .chat-send-btn.is-busy).
    function setThreadBusy(busy) {
      textarea.disabled = busy;
      button.disabled = busy;
      button.classList.toggle("is-busy", busy);
      button.setAttribute("aria-label", busy ? "Asking…" : "Ask a question");
      thread.querySelectorAll("[data-chat-edit-btn]").forEach(function (btn) { btn.disabled = busy; });
    }

    // Copies a bubble's current plain text to the clipboard and briefly flashes
    // the button to confirm it worked - see the [data-chat-copy-btn] click
    // handler further down.
    function copyBubbleText(copyBtn) {
      var bodyEl = copyBtn.closest(".chat-message").querySelector(".chat-message-body");
      var text = bubbleText(bodyEl);
      if (!navigator.clipboard || !navigator.clipboard.writeText) return;
      navigator.clipboard.writeText(text).then(function () {
        copyBtn.classList.add("is-copied");
        copyBtn.setAttribute("aria-label", "Copied!");
        setTimeout(function () {
          copyBtn.classList.remove("is-copied");
          copyBtn.setAttribute("aria-label", "Copy answer");
        }, 1500);
      });
    }

    // Reads a fetch() Response's body as newline-delimited JSON and forwards each
    // parsed event to onEvent as it arrives - shared by the main "Ask" submit
    // handler and the edit-and-resend flow below, since both talk to a server
    // endpoint streaming the exact same event shapes. onFinish runs exactly once,
    // whether the stream ended in {"error"}, {"done"}, a dropped connection, or a
    // fetch() that failed outright.
    function runChatStream(url, requestBody, onEvent, onFinish) {
      var finished = false;
      function finishOnce() {
        if (finished) return;
        finished = true;
        onFinish();
      }

      fetch(url, { method: "POST", body: requestBody })
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
                finishOnce();
                return;
              }

              buffer += decoder.decode(result.value, { stream: true });
              var lines = buffer.split("\n");
              buffer = lines.pop();

              lines.forEach(function (line) {
                if (!line.trim()) return;
                var event;
                try {
                  event = JSON.parse(line);
                } catch (parseError) {
                  return;
                }
                onEvent(event);
                if (event.error || event.done) finishOnce();
              });

              return pump();
            });
          }

          return pump();
        })
        .catch(function () {
          onEvent({ error: "Something went wrong asking this - try again." });
          finishOnce();
        });
    }

    function showErrorIn(body, message) {
      body.innerHTML = "";
      var p = document.createElement("p");
      p.className = "detail-card-empty stream-error";
      p.textContent = message;
      body.appendChild(p);
      scrollToBottom();
    }

    // Enter submits the question (Shift+Enter still inserts a newline, for a
    // question that genuinely needs more than one line) - the composer is a
    // <textarea> rather than a single-line <input> so a long question can still
    // wrap and be reviewed before sending, but a chat composer's Enter key is
    // expected to send, not just add a blank line.
    textarea.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
        }
      }
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = textarea.value.trim();
      if (!question) return;

      var questionBubble = addBubble("user", question);
      textarea.value = "";
      setThreadBusy(true);

      var answer = addBubble("assistant", "");
      var fullText = "";

      var requestBody = new URLSearchParams();
      requestBody.append("question", question);

      runChatStream(form.dataset.streamUrl, requestBody, function (chatEvent) {
        if (chatEvent.question_id) {
          setMessageId(questionBubble.bubble, chatEvent.question_id);
        } else if (chatEvent.error) {
          showErrorIn(answer.body, chatEvent.error);
        } else if (chatEvent.done) {
          fullText = chatEvent.text || fullText;
          renderBodyText(answer.body, fullText, false);
          scrollToBottom();
        } else if (chatEvent.delta) {
          fullText += chatEvent.delta;
          renderBodyText(answer.body, fullText, true);
          scrollToBottom();
        }
      }, function () {
        setThreadBusy(false);
        textarea.focus();
      });
    });

    // --- Edit an earlier question and resend it ---
    //
    // Since this conversation is a single linear thread (not a branching one -
    // see models/literature_chat_message.py), editing a question discards
    // everything the thread held after it (its old answer, and anything asked
    // since) before a fresh answer replaces it - the server does the actual
    // discarding (edit_and_truncate_message()); this only needs to remove the
    // same bubbles from view and then stream the new answer in, the same way the
    // compose form above does for a brand new question.

    function enterEditMode(bubble) {
      if (bubble.querySelector("[data-chat-edit-form]")) return; // already editing
      var body = bubble.querySelector(".chat-message-body");
      var actions = bubble.querySelector(".chat-message-actions");
      body.hidden = true;
      if (actions) actions.hidden = true;

      var editForm = document.createElement("form");
      editForm.className = "chat-edit-form";
      editForm.setAttribute("data-chat-edit-form", "");

      var editTextarea = document.createElement("textarea");
      editTextarea.rows = 2;
      editTextarea.value = bubbleText(body);
      editForm.appendChild(editTextarea);

      var actions = document.createElement("div");
      actions.className = "chat-edit-actions";

      var resendBtn = document.createElement("button");
      resendBtn.type = "submit";
      resendBtn.className = "btn btn-inline btn-sm";
      resendBtn.textContent = "Resend";
      actions.appendChild(resendBtn);

      var cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "btn btn-secondary btn-inline btn-sm";
      cancelBtn.textContent = "Cancel";
      cancelBtn.setAttribute("data-chat-edit-cancel", "");
      actions.appendChild(cancelBtn);

      editForm.appendChild(actions);
      bubble.appendChild(editForm);
      editTextarea.focus();
      editTextarea.selectionStart = editTextarea.selectionEnd = editTextarea.value.length;

      editTextarea.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (typeof editForm.requestSubmit === "function") {
            editForm.requestSubmit();
          } else {
            editForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
          }
        } else if (event.key === "Escape") {
          exitEditMode(bubble);
        }
      });

      editForm.addEventListener("submit", function (event) {
        event.preventDefault();
        submitEdit(bubble, editTextarea.value.trim());
      });
    }

    function exitEditMode(bubble) {
      var editForm = bubble.querySelector("[data-chat-edit-form]");
      if (editForm) editForm.remove();
      var body = bubble.querySelector(".chat-message-body");
      if (body) body.hidden = false;
      var actions = bubble.querySelector(".chat-message-actions");
      if (actions) actions.hidden = false;
    }

    function submitEdit(bubble, newQuestion) {
      if (!newQuestion) return;
      var messageId = bubble.dataset.messageId;
      if (!messageId) return; // the Edit button only appears once an id is known

      // Drop every turn the server is about to drop too - this question's own
      // old answer, and anything asked after it. Each turn is a .chat-row (the
      // avatar + this .chat-message bubble are siblings within one row, so
      // bubble.nextElementSibling never reaches the next turn - walk from the
      // row instead.
      var row = bubble.closest(".chat-row") || bubble;
      var node = row.nextElementSibling;
      while (node) {
        var toRemove = node;
        node = node.nextElementSibling;
        toRemove.remove();
      }

      exitEditMode(bubble);
      var questionBody = bubble.querySelector(".chat-message-body");
      renderBodyText(questionBody, newQuestion, false);
      setThreadBusy(true);

      var answer = addBubble("assistant", "");
      var fullText = "";

      var resendUrl = form.dataset.streamUrl.replace(/\/stream$/, "/messages/" + messageId + "/resend");
      var requestBody = new URLSearchParams();
      requestBody.append("question", newQuestion);

      runChatStream(resendUrl, requestBody, function (chatEvent) {
        if (chatEvent.question_id) {
          return; // already know this bubble's id - it's being rewritten in place
        } else if (chatEvent.error) {
          showErrorIn(answer.body, chatEvent.error);
        } else if (chatEvent.done) {
          fullText = chatEvent.text || fullText;
          renderBodyText(answer.body, fullText, false);
          scrollToBottom();
        } else if (chatEvent.delta) {
          fullText += chatEvent.delta;
          renderBodyText(answer.body, fullText, true);
          scrollToBottom();
        }
      }, function () {
        setThreadBusy(false);
      });
    }

    thread.addEventListener("click", function (event) {
      var editBtn = event.target.closest("[data-chat-edit-btn]");
      if (editBtn && !editBtn.disabled) {
        var bubble = editBtn.closest(".chat-message");
        if (bubble) enterEditMode(bubble);
        return;
      }
      var cancelBtn = event.target.closest("[data-chat-edit-cancel]");
      if (cancelBtn) {
        var editingBubble = cancelBtn.closest(".chat-message");
        if (editingBubble) exitEditMode(editingBubble);
        return;
      }
      var copyBtn = event.target.closest("[data-chat-copy-btn]");
      if (copyBtn) {
        copyBubbleText(copyBtn);
      }
    });
  });
});
