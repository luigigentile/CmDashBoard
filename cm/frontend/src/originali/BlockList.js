import React, { useState,useEffect } from 'react';
import { gql} from "@apollo/client";

import {useQuery} from "@apollo/client";
// import {ALL_BLOCK_ORDERBY_NAME} from '../graphql'


export default function BlockList(props) {
const blockIncrement = 20

const [limit, setLimit] = useState(20)
const [idSelezionato, setIdSelezionato] = useState(0)


const ALL_BLOCK_ORDERBY_NAME = gql`
 {
  allBlock(orderBy: "name", limit : ${limit}) {
    id
    name
    created
       
  }
}
 `
const { loading, error,  data:allBlock} = useQuery(ALL_BLOCK_ORDERBY_NAME, );
if (loading) return <p>Loading...</p>;
if (error) return <p>Errore nel caricare la pagina  :</p>;


function moreBlock() {
    setLimit(limit+blockIncrement)
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




//    MAKE LIST OF block
const blocks = allBlock.allBlock.map((x) => {
  return (
 <li  id = {x.id} style={{fontWeight: getPeso(x.id)}}  key= {x.id} onClick = {() => handleOnClick(x.id)}  > {x.name}    </li> 
  )}
);

 
  // 

  //   
  return (
    <div>
  BLOCK LIST
  {allBlock.allBlock.length}
    {blocks}
  <button onClick={() => moreBlock()}>NEXT</button>

</div>
  );
  
}





