import type {Metadata} from 'next';
import {ReferenceCabinet} from '@/components/reference/cabinet';
export const metadata:Metadata={title:'Демонстрация AdPilot',robots:{index:false,follow:false}};
export default function DemoLayout({children}:{children:React.ReactNode}){return <ReferenceCabinet>{children}</ReferenceCabinet>;}
