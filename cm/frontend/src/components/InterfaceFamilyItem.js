import React, { useState } from 'react';
import InterfaceTypeItem from './InterfaceTypeItem'

export default function InterfaceFamilyItem(props) {

  const [idSelezionato, setIdSelezionato] = useState(0)


  function showInterfaceType(e,varId) {
        if (varId === idSelezionato) {
          setIdSelezionato(0)
        }
        else {
          setIdSelezionato(varId)
    }
  }

  return (
     <div className="row " style={{ fontSize: 15 } } > 
          <div className="col-lg-3 border-bottom" >
            <h4 onClick = {(e) => showInterfaceType(e,props.interfaceFamily.id)}> {props.interfaceFamily.label}</h4>
          </div>
          <div className="col-lg-2 border-bottom" >
            <h4> {props.interfaceFamily.interfaceTypeCount} <span className = "mt-n4" style={{ fontSize: 15 } } >  </span> </h4>
        
        
          </div>
          <div className="col-lg-6" >

          { idSelezionato === props.interfaceFamily.id ?
            <InterfaceTypeItem   interfaceType = {props.interfaceFamily.interfaceType}/>
            : null }



       
          </div>


    </div>


  


  );
  
}


