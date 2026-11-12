## Next: connect your phone (about 1 minute)

```sh
hermes plugins enable hermes-notify
hermes notify setup
```

`hermes notify setup` signs you in to Notify (free; it creates an account if you don't have one), saves the API key to this profile, turns the plugin on, links you to the phone app, sends a test notification, and sends Hermes's command approvals to your phone (the terminal prompt stays as the fallback). Skip that last step with `--no-approvals`.

It works right away, even in open sessions. Try:

- *"Tell me on my phone when the tests finish."*
- *"Run the migration and keep me posted on my phone."*
- *"Ask me on my phone before you deploy, and wait for my answer."*

Something not arriving? `hermes notify status` shows the key, the plugin version, approvals and your phones, and says what to fix.
