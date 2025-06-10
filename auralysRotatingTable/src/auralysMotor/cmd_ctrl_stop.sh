
args=("$@")
echo wget -qO- http://192.168.10.223/ctrl/stop
wget -qO- http://192.168.10.223/ctrl/stop
