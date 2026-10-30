// Purpose
// -------
// Connect exported HTML pages to the matching local portable-tools launcher.
//
// Inputs
// ------
// Current script data-root/data-package values, page location, and optional
// window.MoralesConnection origin; the default local origin is port 5013.
//
// Outputs
// -------
// Expose MoralesPortable.ready, rebase, and connect; redirect unconfigured
// packages to setup and show a local-launcher dialog after connection failures.

/* Shared by every HTML page in the distribution. No scientific data is edited. */
(() => {
  // Resolve this exported package and the launcher origin chosen for its session
  const connectionScript = document.currentScript;
  const packageRoot = new URL(connectionScript.dataset.root, location.href);
  const packageId = connectionScript.dataset.package;
  const connection = window.MoralesConnection || {origin: 'http://127.0.0.1:5013'};
  const origin = connection.origin;
  // Purpose: translate an exported file URL to the launcher file-serving route.
  // Inputs: current location and package root; Outputs: original HTTP URL or local /files URL.
  const localTarget = () => {
    if (location.protocol !== 'file:') return location.href;
    return origin + '/files/' + location.href.slice(packageRoot.href.length);
  };
  // Build the setup/retry dialog before exposing the connection promise
  const dialog = document.createElement('dialog');
  dialog.innerHTML = '<form method="dialog"><h2>Local tools setup</h2>' +
    '<p>The Bokeh tools need the included local launcher.</p>' +
    '<p>Open <strong>Start Tools.command</strong> (macOS), <strong>Start Tools.bat</strong> (Windows), ' +
    'or <strong>Start Tools.sh</strong> (Linux) in the downloaded folder. Keep its window open.</p>' +
    '<p>The setup page will then ask for your <strong>Data</strong> directory.</p>' +
    '<p data-state role="status"></p><button type="button" data-retry>Try again</button> ' +
    '<button value="close">View figures only</button></form>';
  Object.assign(dialog.style, {maxWidth: '36rem', padding: '1.5rem', borderRadius: '8px',
    fontFamily: 'system-ui', lineHeight: '1.5'});
  // Attach the dialog immediately or wait until the document body exists
  const mounted = new Promise(resolve => {
    const mount = () => {document.body.append(dialog); resolve();};
    if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount, {once:true});
  });
  // Purpose
  // -------
  // Rebase a recognized loopback Bokeh application URL onto the selected local origin.
  //
  // Inputs
  // ------
  // url: link resolved relative to the current page.
  //
  // Outputs
  // -------
  // Return the matching-origin URL with its path/query/hash; reject unsupported hosts or paths.
  function rebase(url) {
    const target = new URL(url, location.href);
    if (['localhost', '127.0.0.1'].includes(target.hostname) &&
        /^\/(?:integrated_komega|observation_komega|komega|gaussian_filter|magnetogram)_bokeh_app\/?$/.test(target.pathname)) {
      return origin + target.pathname + target.search + target.hash;
    }
    throw Error('Invalid local Bokeh URL.');
  }
  // Purpose
  // -------
  // Verify launcher package identity and route the page through setup when needed.
  //
  // Inputs
  // ------
  // Read the enclosing dialog, package identifier, origin, and current page location.
  //
  // Outputs
  // -------
  // Resolve to true when configured on HTTP; otherwise redirect or show the dialog
  // and resolve to false. Abort the status request after 2.5 seconds.
  async function connect() {
    await mounted;
    try {
      // Bound the local status request and always clear its abort timer
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 2500);
      let response;
      try { response = await fetch(origin + '/portable/status', {cache:'no-store', signal:controller.signal}); }
      finally { clearTimeout(timer); }
      const state = await response.json();
      // Reject a launcher serving a different exported package
      if (state.package_id !== packageId) throw Error('The launcher for this package is not running.');
      const target = localTarget();
      // Ask the launcher to select the data directory before opening tools
      if (!state.configured) {
        location.replace(origin + '/setup?next=' + encodeURIComponent(target));
        return false;
      }
      if (location.protocol === 'file:') { location.replace(target); return false; }
      if (dialog.open) dialog.close();
      return true;
    } catch (error) {
      dialog.querySelector('[data-state]').textContent = error.message;
      if (!dialog.open) dialog.showModal();
      return false;
    }
  }
  // The launcher writes the selected port after this file may already be open.
  dialog.querySelector('[data-retry]').addEventListener('click', () => location.reload());
  // Rebase supported local-tool links just before normal browser navigation
  document.addEventListener('click', event => {
    const anchor = event.target.closest('a[href]');
    if (!anchor) return;
    try {
      const next = rebase(anchor.href);
      if (next !== anchor.href) anchor.href = next;
    } catch (_) {}
  });
  // Start the initial connection and expose retry/rebase hooks to exported pages
  window.MoralesPortable = {ready: connect(), rebase, connect};
})();
