module.exports = {
  apps: [{
    name: "openclaw",
    script: "/root/openclaw/openclaw.mjs",
    args: "gateway",
    cwd: "/root/openclaw",
    node_args: "--max-old-space-size=4096",
    env_file: "/root/openclaw/.env",
    restart_delay: 3000,
    max_restarts: 10,
    watch: false,
    autorestart: true,
  }]
}
