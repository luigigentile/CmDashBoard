 import {  ApolloClient, InMemoryCache } from "@apollo/client";
   
   const client = new ApolloClient({
     uri: "http://127.0.0.1:8000/graphiql",
         cache: new InMemoryCache()
   });
 
 export default client


 // import { ApolloClient, createHttpLink, InMemoryCache } from '@apollo/client';
 // import { setContext } from '@apollo/client/link/context';
 // 
 // const httpLink = createHttpLink({
 //    uri: "https://cm-app-prod.herokuapp.com/ace/api/",
/// /      uri: "http://127.0.0.1:8000/graphiql",
// 
 //    fetchOptions: {
 //      mode: 'no-cors',
 //     },
 //     
 //   });
 //   
 //   const authLink = setContext((_, { headers }) => {
 //     // get the authentication token from local storage if it exists
 //     const token = 'd271ee5bd703289888cccabbf1605e69cebd5246'
 //     // return the headers to the context so httpLink can read them
 //     return {
 //       headers: {
 //         ...headers,
 //         authorization: token ? `Bearer ${token}` : "",
 //         method:'GET'
 //       }
 //     }
 //   });
 //   
 //   const client = new ApolloClient({
 //     link: authLink.concat(httpLink),
 //     cache: new InMemoryCache()
 //   });
 //  
 //  
 //  export default client






//   import { ApolloClient, InMemoryCache, HttpLink } from "@apollo/client"
//   import { onError } from "@apollo/client/link/error"
//   
//   const httpLink = new HttpLink({ uri: "https://cm-app-prod.herokuapp.com/ace/api/" })
//   
//   const loginLink = onError(({ networkError }) => {
//     if (
//       networkError &&
//       "statusCode" in networkError &&
//       [401, 403].includes(networkError.statusCode)
//     ) {
//       window.location.assign(
//         `/admin/login/?next=${encodeURIComponent(
//           window.location.pathname + window.location.search
//         )}`
//       )
//     }
//   })
//   
//   const client = new ApolloClient({
//     cache: new InMemoryCache(),
//     link: loginLink.concat(httpLink),
//   })
//   
//   export default client
// 


