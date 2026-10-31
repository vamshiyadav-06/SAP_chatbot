// Applies the saved light/dark preference before React renders, to avoid a flash of the wrong theme.
// An external file (not an inline <script>) so the Content-Security-Policy can forbid inline scripts.
(function () {
  try {
    if (localStorage.getItem('clyptus-appearance') === 'light') {
      document.documentElement.classList.remove('dark');
    } else {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {
    document.documentElement.classList.add('dark');
  }
})();
