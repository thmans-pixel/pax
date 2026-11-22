#!/bin/bash
# Aides communes aux scripts du paquet.

installer_code() {
    mkdir -p "$install_dir"
    cp -a "$YNH_APP_BASEDIR/app" "$YNH_APP_BASEDIR/donnees" "$YNH_APP_BASEDIR/scenarios" \
          "$YNH_APP_BASEDIR/requirements.txt" "$install_dir/"
    python3 -m venv "$install_dir/venv"
    "$install_dir/venv/bin/pip" install --quiet -r "$install_dir/requirements.txt"
    chown -R "$app:$app" "$install_dir"
    chmod -R o-rwx "$install_dir"
}
