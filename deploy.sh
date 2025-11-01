#!/bin/sh
curl -fsSL https://pixi.sh/install.sh | sh
export PATH="$HOME/.pixi/bin:$PATH"
pixi global install kisiac

echo "Deployment complete. Re-login to use kisiac."