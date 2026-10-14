import {createRoot} from 'react-dom/client';
import App from './App';
import Print from './Print';
import AuditPreview from './AuditPreview';
import './style.css';
const params=new URLSearchParams(location.search);
createRoot(document.getElementById('root')!).render(params.has('audit')?<AuditPreview/>:params.has('print')?<Print/>:<App/>);
