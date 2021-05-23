import React from 'react'



export default class TotalValue extends React.Component {
 
    constructor(props) {
        super(props);
    
       }

  

render() {
// 
const Totali = (
  <div>
<h2> sono in Total Value </h2>
  {this.props.countBlockType.countBlockType[0].count}
  </div>
  )

  return (
    <div>
 
  <div className="row">
            <div className="col-lg-2 border-bottom ">
                <h4> {this.props.countBlockType.countBlockType[0].blockType}</h4>
          </div>
          <div className="col-lg-2 border-bottom ">
                <h4> {this.props.countBlockType.countBlockType[1].blockType}</h4>
          </div>
    </div>

    <div className="row">
            <div className="col-lg-2 border-bottom ">
                <h4> {this.props.countBlockType.countBlockType[0].count}</h4>
          </div>
          <div className="col-lg-2 border-bottom ">
                <h4> {this.props.countBlockType.countBlockType[1].count}</h4>
          </div>
    </div>


    </div>
  );
}
}

