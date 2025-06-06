
args=("$@")
echo wget -qO- http://192.168.10.32/ctrl/stop
wget -qO- http://192.168.10.32/ctrl/stop
