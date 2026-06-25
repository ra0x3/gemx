// Gemini.py Prompt Injection Test
// Paste this whole file into the browser console on gemini.google.com.
// It auto-runs with "Hey, how are you?" and prints the response.
// Re-paste to run again; call window.runGeminiPrompt("...") for a custom prompt.

(() => {
  const SEL = {
    input: '.ql-editor[contenteditable="true"]',
    send: 'button[aria-label="Send message"]',
    responseCandidates: [
      'message-content .markdown',
      'message-content',
      'model-response .markdown',
      'model-response',
      '.model-response-text',
      '.markdown',
    ],
  };

  function getInput() {
    return document.querySelector(SEL.input) ||
           document.querySelector('[aria-label="Enter a prompt for Gemini"]');
  }

  function getSendButton() {
    return document.querySelector(SEL.send) ||
           Array.from(document.querySelectorAll('button')).find(b =>
             b.querySelector('mat-icon[data-mat-icon-name="arrow_upward"]') !== null);
  }

  async function waitFor(fn, timeoutMs = 8000, intervalMs = 150) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const v = fn();
      if (v) return v;
      await new Promise(r => setTimeout(r, intervalMs));
    }
    return null;
  }

  // Inject via execCommand('insertText'). Synthetic InputEvents are ignored by
  // Quill (isTrusted=false), but execCommand routes through the browser's
  // native editing pipeline, firing trusted beforeinput/input that Quill honors.
  function injectViaExecCommand(editor, text) {
    editor.focus();
    const sel = window.getSelection();
    sel.removeAllRanges();
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    sel.addRange(range);
    const ok = document.execCommand('insertText', false, text);
    console.log(`   execCommand insertText returned: ${ok}`);
  }

  // Fallback: simulate a clipboard paste, which is what works manually.
  function injectViaPaste(editor, text) {
    editor.focus();
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    editor.dispatchEvent(new ClipboardEvent('paste', {
      bubbles: true, cancelable: true, clipboardData: dt,
    }));
  }

  function readBestResponse() {
    for (const sel of SEL.responseCandidates) {
      const els = Array.from(document.querySelectorAll(sel));
      if (!els.length) continue;
      let best = '';
      els.forEach(el => {
        const t = el.innerText || el.textContent || '';
        if (t.length > best.length) best = t;
      });
      if (best.trim().length > 0) return { sel, text: best };
    }
    return null;
  }

  async function runGeminiPrompt(promptText = 'Hey, how are you?') {
    console.log(`\n=== GEMINI PROMPT TEST: "${promptText}" ===`);

    const editor = getInput();
    if (!editor) {
      console.error('❌ Input not found');
      return;
    }

    console.log('→ injecting via execCommand...');
    injectViaExecCommand(editor, promptText);

    let typed = (editor.innerText || '').trim();
    if (!typed) {
      console.log('→ execCommand empty, trying paste event...');
      injectViaPaste(editor, promptText);
      typed = (editor.innerText || '').trim();
    }
    console.log(`   editor now shows: "${typed}" (${typed.length} chars)`);

    console.log('→ waiting for send button to enable...');
    const sendBtn = await waitFor(getSendButton);
    if (!sendBtn) {
      console.error('❌ Send button never appeared — Quill did not register the input');
      return;
    }
    console.log(`✅ send button ready (aria-label="${sendBtn.getAttribute('aria-label')}"), clicking...`);
    sendBtn.click();

    console.log('⏳ waiting for response...');
    const start = Date.now();
    let lastLen = 0;
    let stable = 0;
    let best = null;

    const result = await new Promise(resolve => {
      const iv = setInterval(() => {
        const elapsed = Math.floor((Date.now() - start) / 1000);
        const hit = readBestResponse();
        if (hit) {
          best = hit;
          const len = hit.text.length;
          if (len > lastLen) {
            console.log(`   [${elapsed}s] growing: ${len} chars via '${hit.sel}'`);
            lastLen = len;
            stable = 0;
          } else {
            stable++;
            if (stable >= 3 && len > 0) {
              clearInterval(iv);
              resolve(best);
            }
          }
        } else if (elapsed % 5 === 0) {
          console.log(`   [${elapsed}s] no response yet...`);
        }
        if (Date.now() - start > 120000) {
          clearInterval(iv);
          resolve(best);
        }
      }, 1000);
    });

    console.log('\n=== RESULT ===');
    if (result && result.text) {
      console.log(`selector: '${result.sel}'`);
      console.log(`length:   ${result.text.length} chars`);
      console.log('response:\n================');
      console.log(result.text);
      console.log('================');
      window.lastGeminiResponse = result.text;
    } else {
      console.error('❌ No response captured (turn may have errored / reverted)');
    }
  }

  window.runGeminiPrompt = runGeminiPrompt;
  console.log('[loaded] auto-running runGeminiPrompt("Hey, how are you?")');
  runGeminiPrompt('Hey, how are you?').catch(e => console.error('runGeminiPrompt threw:', e));
})();
