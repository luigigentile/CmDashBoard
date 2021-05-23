import React, { useState } from 'react';
import Bar from './chart/Bar'
import CategoryItem from './CategoryItem'



  export default function CategoryList(props) {
    
  var subSons = []
  const [showSon, setShowSon] = useState(false)
  const [parentLabel, setParentLabel] = useState("")
  const [idSelezionato, setIdSelezionato] = useState(0)
 

//  set the weight to bold of item selected
    function setWeight(varId) {
      if (varId === idSelezionato) {
        return ("bold")
      }
      return ("")  
    }

  
    //    MAKE LIST OF SONS
 //    const sonsList = props.sons.map((x) => {
 //        return (
 //       <li style={{fontWeight: setWeight(x.id),} }   name= {x.allSonsCount} id = {x.label} key = {x.id}   onClick = {(e) => showSons(e,x.id)} >{x.label} {x.allBlockCount} </li> 
 //        )}
 //    );
 //    

    const sonsList = props.sons.map((x) => {
      return (
     <CategoryItem category = {x}   />
      )}
      );





    function getSons(obj) {
        return ( parentLabel === obj.parent) 
     }
    
     function showSons(e,varId) {
      var previosParentLabel = parentLabel 
      setParentLabel(e.target.id)
      setIdSelezionato(varId)
       
       
     
      if (!parentLabel === previosParentLabel || parentLabel === "") {
        setShowSon(!showSon)
       }
      }
         
        
    subSons = props.allCategory.allCategory.filter(getSons);
    var title = "Component by Category: " + parentLabel


    var legend = {
      titleAsseX : "Component",
      titleAsseY : "Components' Number",
      labelTextColor: "#ffffff"
    }
    
//    {subSons.length>0 ?    <Bar   sons = {subSons} height = {600} title = {title} legend = {legend} /> : null }

    return (
      <div className="row " > 
      
        <div className="col-lg-7 ml-n2" >
          {sonsList}
        </div>
             
          <div className="col-lg-4 " >
       
         <Bar   sons = {props.sons} height = {800} title = {title} legend = {legend} /> 
        
      </div>
      </div>

  );
  
}
