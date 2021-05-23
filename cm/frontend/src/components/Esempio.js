import React, { useState,useEffect } from 'react';
import {ALL_BLOCK} from '../graphql'
import {useQuery} from "@apollo/client";
import BlocksVsCreated from './chart/BlocksVsCreated'
import TotalValue from './chart/TotalValue'
import Pie from './chart/Pie'

import {COUNT_BLOCKTYPE} from '../graphql'



 
export default function Esempio(props) {
  const [contatore, setContatore] = useState(0);
  useEffect(() => {
    document.title = `DashBoard`;
    console.log(contatore)
  } , [contatore] );
  
  const { loading, error,  data:allBlock } = useQuery(ALL_BLOCK);
  const { data: countBlockType } = useQuery(COUNT_BLOCKTYPE);
  if (loading) return <p>Loading...</p>;
  if (error) return <p>Error :</p>;
  
  
  return (
    <div>
       <TotalValue countBlockType = {countBlockType} />
       <div className="row " > 
          <div className="col-lg-6 " >
              <Pie data = {countBlockType.countBlockType}   />
            </div>
          
            <div className="col-lg-6 " >
            <BlocksVsCreated data = {allBlock}  /> 
            </div>
        </div>
     </div>
   );
  }



