
args=("$@")

verbose=1

for i in $args; do
  case $i in
    -q|--quiet)
      verbose=0
      shift # past argument=value
      ;;
    --default)
      DEFAULT=YES
      shift # past argument with no value
      ;;
    -*|--*)
      echo "Unknown option $i"
      exit 1
      ;;
    *)
      ;;
  esac
done

if [[ $verbose -gt 0 ]]; then
   echo "wget -qO- http://192.168.10.34/position/get"
   echo $verbose
fi

wget -qO- http://192.168.10.34/position/get
