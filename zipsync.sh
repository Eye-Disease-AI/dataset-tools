trap 'kill 0; exit 130' INT

if [ -z "$3" ]; then
    echo "$0 <wg_if> <dir_to_send> <user@remote:/path>"
    exit 1
fi

vpn="$HOME/.wireguard/$1.conf"
sudo wg-quick up "$vpn"
rsync -avP --inplace --include='*/' --include='*.zip' --exclude='*' "$PWD/$2" "$3"
sudo wg-quick down "$vpn"