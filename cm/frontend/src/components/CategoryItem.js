
export default function CategoryItem(props) {


  return (
     <div className="row "  > 
          <div className="col-lg-6 border-bottom" >
            <h6> {props.category.label}</h6>
          </div>
          <div className="col-lg-3 border-bottom" >
            <h6> {props.category.allBlockCount}  </h6>
          </div>
          <div className="col-lg-3" >
          </div>


    </div>


  


  );
  
}


