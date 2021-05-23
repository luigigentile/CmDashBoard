import React, { useState,useEffect } from 'react';
import { gql} from "@apollo/client";

import {useQuery} from "@apollo/client";


export default function BlockManageList(props) {
  const allBlock = props.allBlock
  const [idSelezionato, setIdSelezionato] = useState(0)
  const blockIncrement = 20


 function moreBlock() {
  props.setLimit(props.limit+blockIncrement)
 }
 
 function handleOnClick(varId) {
    setIdSelezionato(varId)
 }
 
 function getPeso(varId) {
   if (varId === idSelezionato) {
     return ("bold")
   }
  
   return ("")  
 }
// 



//    MAKE LIST OF block
 const blocks = allBlock.allBlock.map((x) => {
  if (x.name.indexOf(props.searchText) === -1) {
    return null;
    }
  else {
   return (
  <li  id = {x.id} style={{fontWeight: getPeso(x.id)}}  key= {x.id} onClick = {() => handleOnClick(x.id)}  > {x.name}    </li> 
   )}
 }
 );

 
  // 
  // <button onClick={() => moreBlock()}>NEXT</button>

  //   
  return (
    <div>
  BLOCK manage LIST 
  {blocks}
  <button onClick={() => moreBlock()}>NEXT</button>

</div>
  );
  
}





