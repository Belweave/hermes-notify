// The separate Web Dashboard discovers backend manifests too. Register a hidden
// explanatory component so it does not try to load a nonexistent default entry.
(function () {
  const sdk = window.__HERMES_PLUGIN_SDK__;
  const registry = window.__HERMES_PLUGINS__;
  if (!sdk || !registry) return;
  registry.register('hermes-notify', function NotifyCompanionLocation() {
    return sdk.React.createElement('p', { className: 'hermes-notify-dashboard' },
      'Open Hermes Pocket in Hermes Desktop or its browser Webapp. This Web Dashboard supplies the read-only status API. Notify is the phone surface.');
  });
})();
