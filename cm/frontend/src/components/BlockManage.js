import React, { useState,useEffect } from 'react';
import { gql} from "@apollo/client";

import {useQuery} from "@apollo/client";
import BlockManageSearchBar from './BlockManageSearchBar'
import BlockManageList from './BlockManageList'

// import {ALL_BLOCK_ORDERBY_NAME} from '../graphql'

export default function BlockManage(props) {
const blockIncrement = 20

const [limit, setLimit] = useState(20)
const [searchText, setSearchText] = useState("")

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
 
  return (
    <div>
    <BlockManageSearchBar searchText = {searchText} setSearchText = {setSearchText} setLimit = {setLimit} />
    <BlockManageList searchText = {searchText} allBlock =  {allBlock} limit = {limit} setLimit = {setLimit} />

</div>
  );
  
}





