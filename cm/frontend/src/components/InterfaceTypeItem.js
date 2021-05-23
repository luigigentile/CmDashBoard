import React, { useState } from 'react';

export default function InterfaceTypeItem(props) {

  //    MAKE LIST OF interfaceType 
  const interfaceTypeList = props.interfaceType.map((x) => {
    return (
     <li   key = {x.id}  > {x.name} </li> 
 
    )}
);
 

  return (
    <div>
     <div className="row " style={{ fontSize: 15 } } > 
      <div className="col-lg-12 border-bottom" > 

      </div>
      <ul>
      {interfaceTypeList}
      </ul>


    </div>


    </div>


  );
  
}


