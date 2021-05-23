
export default function ManufacturerItem(props) {
  let persentagePartCount = (props.manufacturer.partCount/props.totalPartCount*100).toFixed(2)


  return (
     <div className="row " style={{ fontSize: 15 } } > 
          <div className="col-lg-3 border-bottom"  >
            <h4> {props.manufacturer.name}</h4>
          </div>
          <div className="col-lg-2 border-bottom" >
            <h4> {props.manufacturer.partCount} <span className = "mt-n4" style={{ fontSize: 15 } } > ({persentagePartCount}%) </span> </h4>
          </div>
          <div className="col-lg-6" >
          </div>


    </div>


  


  );
  
}


