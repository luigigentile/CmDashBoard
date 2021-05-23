import React, { useState,useEffect } from 'react';

import {gql, useQuery} from "@apollo/client";




export default function Category(props) {

  const USER1 = gql`
  query user {
      user {
        username
      }
    }
   `

const USER2 = gql`
 {
  allBlock {
    id
    name
    created
       
  }
}
 `

const USER = gql`
query parts {
    parts {
      edges{
        node {
          id
        }
      }
    
    
 
  }
  }
`





//   LOAD ALL CATEGORY FROM DATABASE WITH REFETCH
 const { loading, error,  data:data, refetch,networkStatus } = useQuery(USER);
 if (loading) return <p>Loading...</p>;
 alert("Ho caricato nuovamente categories")
// if (error) return <p>Errore nel caricare la pagina  : {JSON.stringify(error)} </p>;
  if (error) return <p>Errore nel caricare la pagina   </p>;
 alert("No error")

    

      
  //  <TotalCategories allCategory = {allCategory.allCategory}  categoryLevelZero = {props.categorySelected} sons = {sons} />
    return (
      <div className = "ml-2">
      <h1> all category</h1>
     
</div>
  );
  
}

