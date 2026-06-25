  // Gemini.py Debugging Console Script
  // Paste this into the browser console on gemini.google.com
  //
  // Updated for the current Gemini UI (2026):
  //   Input:  rich-textarea > .ql-editor[contenteditable="true"]
  //           (stable handle: [aria-label="Enter a prompt for Gemini"])
  //   Send:   gem-icon-button > button[aria-label="Send message"]
  //           (icon: mat-icon[data-mat-icon-name="arrow_upward"])
  //   Reply:  message-content / .markdown (verify via probe below)

  console.log("=== GEMINI.PY SELECTOR DEBUG TOOL ===");

  // Canonical selectors the python script should use.
  const SELECTORS = {
      input: '.ql-editor[contenteditable="true"]',
      inputByLabel: '[aria-label="Enter a prompt for Gemini"]',
      inputWrapper: 'rich-textarea',
      send: 'button[aria-label="Send message"]',
      // Candidate reply containers, most-specific first.
      responseCandidates: [
          'message-content .markdown',
          'message-content',
          'model-response .markdown',
          'model-response',
          '.model-response-text',
          '.markdown',
          '[id^="model-response-message-content"]',
      ],
  };

  // Test the selectors the script relies on.
  function testSelectors() {
      const tests = {
          "Input (.ql-editor[contenteditable])": document.querySelector(SELECTORS.input),
          "Input (aria-label 'Enter a prompt for Gemini')": document.querySelector(SELECTORS.inputByLabel),
          "Input wrapper (rich-textarea)": document.querySelector(SELECTORS.inputWrapper),
          "Send Button (aria-label 'Send message')": document.querySelector(SELECTORS.send),
          "Send Button via gem-icon-button": document.querySelector('gem-icon-button > button[aria-label="Send message"]'),
          "Send icon (arrow_upward)": document.querySelector('mat-icon[data-mat-icon-name="arrow_upward"]'),
      };

      console.log("\n📋 SELECTOR TEST RESULTS:");
      for (const [name, element] of Object.entries(tests)) {
          console.log(`${element ? '✅' : '❌'} ${name}: ${element ? 'Found' : 'Not found'}`);
          if (element) {
              console.log(`   → Element:`, element);
          }
      }
  }

  // Find all possible input elements.
  function findInputElements() {
      console.log("\n🔍 SEARCHING FOR INPUT ELEMENTS:");

      const richTextareas = document.querySelectorAll('rich-textarea');
      console.log(`Rich-textarea elements found: ${richTextareas.length}`);
      richTextareas.forEach((rt, i) => {
          console.log(`  Rich-textarea ${i}:`, rt);
          console.log(`    → aria-label: ${rt.getAttribute('aria-label')}`);
      });

      const qlEditors = document.querySelectorAll('.ql-editor');
      console.log(`Quill editors found: ${qlEditors.length}`);
      qlEditors.forEach((qe, i) => {
          console.log(`  Quill editor ${i}:`, qe);
          console.log(`    → Contenteditable: ${qe.contentEditable}`);
          console.log(`    → aria-label: ${qe.getAttribute('aria-label')}`);
          console.log(`    → Classes: ${qe.className}`);
      });

      const contentEditables = document.querySelectorAll('[contenteditable="true"]');
      console.log(`ContentEditable elements found: ${contentEditables.length}`);
      contentEditables.forEach((ce, i) => {
          console.log(`  ContentEditable ${i}: aria-label="${ce.getAttribute('aria-label')}" classes="${ce.className}"`);
      });
  }

  // Find all possible send buttons.
  function findSendButtons() {
      console.log("\n🔍 SEARCHING FOR SEND BUTTONS:");

      const allButtons = Array.from(document.querySelectorAll('button'));
      console.log(`Total buttons found: ${allButtons.length}`);

      const sendButtons = allButtons.filter(btn => {
          const text = (btn.innerText || btn.textContent || '').toLowerCase();
          const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
          const title = (btn.getAttribute('title') || '').toLowerCase();
          const icon = btn.querySelector('mat-icon[data-mat-icon-name="arrow_upward"]');
          return ariaLabel.includes('send') || ariaLabel.includes('submit') ||
                 title.includes('send') || text.includes('send') || icon !== null;
      });

      console.log(`Send/Submit buttons found: ${sendButtons.length}`);
      sendButtons.forEach((btn, i) => {
          console.log(`  Button ${i}:`);
          console.log(`    → Aria-label: "${btn.getAttribute('aria-label')}"`);
          console.log(`    → Icon: ${btn.querySelector('mat-icon')?.getAttribute('data-mat-icon-name')}`);
          console.log(`    → In gem-icon-button: ${btn.closest('gem-icon-button') !== null}`);
          console.log(`    → Element:`, btn);
      });
  }

  // Probe which reply container actually holds model responses.
  function findResponseElements() {
      console.log("\n🔍 SEARCHING FOR RESPONSE ELEMENTS:");

      const probes = [
          'message-content',
          'model-response',
          '.model-response-text',
          '.markdown',
          'response-container',
          '[id^="model-response-message-content"]',
          '[data-test-id*="response"]',
          '[data-test-id*="message"]',
      ];

      probes.forEach(selector => {
          const elements = document.querySelectorAll(selector);
          if (elements.length > 0) {
              const withText = Array.from(elements).filter(el => (el.innerText || '').trim().length > 0);
              console.log(`✅ ${selector}: ${elements.length} matched, ${withText.length} with text`);
              if (withText.length > 0) {
                  const last = withText[withText.length - 1];
                  console.log(`   last text (120c): ${(last.innerText || '').slice(0, 120)}`);
              }
          } else {
              console.log(`❌ ${selector}: none`);
          }
      });
  }

  function getInput() {
      return document.querySelector(SELECTORS.input) ||
             document.querySelector(SELECTORS.inputByLabel) ||
             document.querySelector('[contenteditable="true"]');
  }

  function getSendButton() {
      return document.querySelector(SELECTORS.send) ||
             Array.from(document.querySelectorAll('button')).find(b =>
                 b.querySelector('mat-icon[data-mat-icon-name="arrow_upward"]') !== null);
  }

  // The send button only mounts once the input has text. Poll for it.
  async function waitForSendButton(timeoutMs = 8000) {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
          const btn = getSendButton();
          if (btn) return btn;
          await new Promise(r => setTimeout(r, 200));
      }
      return null;
  }

  // After a reply lands, find which container actually holds it.
  function probeResponseContainers() {
      const probes = [
          'message-content .markdown', 'message-content',
          'model-response .markdown', 'model-response',
          '.model-response-text', '.markdown',
          '[id^="model-response-message-content"]',
          'response-container', '[data-test-id*="response"]',
      ];
      const hits = [];
      for (const sel of probes) {
          const els = Array.from(document.querySelectorAll(sel))
              .filter(el => (el.innerText || '').trim().length > 20);
          if (els.length) hits.push({ sel, count: els.length });
      }
      return hits;
  }

  function firstResponseSelector() {
      for (const sel of SELECTORS.responseCandidates) {
          if (document.querySelector(sel)) return sel;
      }
      return null;
  }

  // Send a test message using current selectors.
  function sendTestMessage(text = "Test message from console") {
      console.log("\n📤 ATTEMPTING TO SEND TEST MESSAGE...");

      const input = getInput();
      if (!input) {
          console.error("❌ No input field found!");
          return;
      }

      input.focus();
      input.classList.remove('ql-blank');
      input.textContent = '';
      const p = document.createElement('p');
      p.textContent = text;
      input.appendChild(p);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      console.log("✅ Text entered into input field");

      setTimeout(() => {
          const sendBtn = getSendButton();
          if (sendBtn) {
              sendBtn.click();
              console.log("✅ Send button clicked");
          } else {
              console.error("❌ Send button not found!");
          }
      }, 500);
  }

  // Print the recommended selectors for gemini.py.
  function getCorrectSelectors() {
      console.log("\n🎯 RECOMMENDED SELECTORS FOR GEMINI.PY:");

      const input = getInput();
      console.log("Input selector to use:");
      if (input && input.classList.contains('ql-editor')) {
          console.log("  → '.ql-editor[contenteditable=\"true\"]'");
      } else if (input) {
          console.log(`  → '[aria-label="${input.getAttribute('aria-label')}"]'`);
      } else {
          console.log("  → ❌ No input found - page may need to load");
      }

      const sendBtn = getSendButton();
      console.log("\nSend button selector to use:");
      if (sendBtn && sendBtn.getAttribute('aria-label')) {
          console.log(`  → 'button[aria-label="${sendBtn.getAttribute('aria-label')}"]'`);
      } else if (sendBtn) {
          console.log("  → 'button:has(mat-icon[data-mat-icon-name=\"arrow_upward\"])'");
      } else {
          console.log("  → ❌ No send button found");
      }

      console.log("\nResponse selector to use:");
      const respSel = firstResponseSelector();
      console.log(respSel ? `  → '${respSel}'` : "  → ❌ none found (send a message first)");
  }

  // Test the full flow with current selectors (async).
  async function testUpdatedSelectors() {
      console.log("\n🚀 Testing updated Gemini selectors...");

      const editor = getInput();
      if (!editor) {
          console.error("❌ Input not found");
          return;
      }
      console.log("✅ Input found, setting text...");
      editor.focus();
      editor.classList.remove('ql-blank');
      editor.textContent = '';
      const p = document.createElement('p');
      p.textContent = 'Hey how are you';
      editor.appendChild(p);
      editor.dispatchEvent(new Event('input', { bubbles: true }));

      console.log("✅ Text set, waiting for send button to mount...");
      const sendBtn = await waitForSendButton();
      if (!sendBtn) {
          console.error("❌ Send button never appeared (input may not have registered text)");
          return;
      }
      console.log(`✅ Send button found (aria-label="${sendBtn.getAttribute('aria-label')}"), clicking...`);
      sendBtn.click();

      console.log("⏳ Waiting for response to generate...");
      // Re-probe after sending, since the reply container mounts on response.
      await new Promise(resolve => setTimeout(resolve, 2500));
      const hits = probeResponseContainers();
      console.log("   Response containers detected after send:", hits);
      const responseSelector = (hits[0] && hits[0].sel) || firstResponseSelector() || '.markdown';
      console.log(`   Using response selector: '${responseSelector}'`);

      let checkCount = 0;
      const initialResponseCount = document.querySelectorAll(responseSelector).length;
      let lastLength = 0;
      let stableCount = 0;

      const checkInterval = setInterval(() => {
          checkCount++;
          const responses = document.querySelectorAll(responseSelector);

          if (responses.length > initialResponseCount) {
              const lastResponse = responses[responses.length - 1];
              const responseText = lastResponse.innerText || lastResponse.textContent || '';
              const currentLength = responseText.length;

              if (currentLength > lastLength) {
                  console.log(`   Response growing: ${currentLength} chars (was ${lastLength})`);
                  lastLength = currentLength;
                  stableCount = 0;
              } else if (currentLength > 0) {
                  stableCount++;
                  if (stableCount >= 3 && currentLength > 50) {
                      console.log(`\n✅ Response complete after ~${checkCount * 2} seconds!`);
                      console.log(`   Final length: ${currentLength} characters`);
                      console.log("\n📝 FULL RESPONSE:");
                      console.log("================");
                      console.log(responseText);
                      console.log("================");
                      clearInterval(checkInterval);
                      window.lastGeminiResponse = responseText;
                      console.log("\n💡 Response saved to window.lastGeminiResponse");
                  }
              }
          } else if (checkCount > 30) {
              console.error(`❌ No response found after 60 seconds`);
              console.log(`   Still have ${responses.length} elements (started with ${initialResponseCount})`);
              clearInterval(checkInterval);
          } else if (checkCount % 5 === 0) {
              console.log(`   Check ${checkCount}: Waiting for response...`);
          }
      }, 2000);
  }

  // Run all tests.
  console.log("\n🚀 Running all tests...\n");
  testSelectors();
  findInputElements();
  findSendButtons();
  findResponseElements();
  getCorrectSelectors();

  console.log("\n💡 QUICK FUNCTIONS:");
  console.log("  • sendTestMessage('your text') - Send a test message");
  console.log("  • testSelectors() - Test current selectors");
  console.log("  • getCorrectSelectors() - Get recommended selectors");
  console.log("  • testUpdatedSelectors() - Full send + response-detection flow");

  console.log("\n=== END OF DEBUG TOOL ===");
